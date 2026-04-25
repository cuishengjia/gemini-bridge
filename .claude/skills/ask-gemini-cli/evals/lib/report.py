"""Render a human-readable Chinese Markdown summary from aggregated stats.

This module deliberately holds **only** presentation logic. All numeric
aggregation happens in `lib.aggregate`; here we just format dicts/dataclasses
into Markdown tables.

The returned string is the full `summary.md` contents — callers decide
whether to write it to disk or emit it on stdout.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from .aggregate import (
    BucketStat,
    OverallStats,
    bucket_stats,
    error_category_distribution,
    llm_score_stats,
    model_used_distribution,
    overall_stats,
    refusal_ok_rows,
    search_call_distribution,
    token_stats,
    top_slow,
    zero_url_ok_rows,
)


# ---------- number formatting ----------


def _fmt_ratio(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x * 100:.1f}%"


def _fmt_num(x: float | int | None, digits: int = 1) -> str:
    if x is None:
        return "-"
    if isinstance(x, int):
        return str(x)
    return f"{x:.{digits}f}"


def _fmt_ms(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x / 1000:.1f}s"


# ---------- table helpers ----------


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render a Markdown table. No trailing newline."""
    sep = "| " + " | ".join(headers) + " |"
    align = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(cells) + " |" for cells in rows)
    return f"{sep}\n{align}\n{body}"


# ---------- section builders ----------


def _section_overview(st: OverallStats, meta: dict[str, Any]) -> str:
    lines = [
        "## 一、总体概览",
        "",
        f"- 生成时间：{meta.get('generated_at', datetime.now().isoformat(timespec='seconds'))}",
        f"- 运行目录：`{meta.get('run_dir', '-')}`",
        f"- 样本总数：{st.total}",
        f"- 成功率（ok）：{st.ok_count}/{st.total} = {_fmt_ratio(st.ok_rate)}",
        f"- 触发 fallback：{st.fallback_count}/{st.total} = {_fmt_ratio(st.fallback_rate)}",
        f"- 平均尝试次数：{_fmt_num(st.mean_attempts, 2)}",
    ]
    return "\n".join(lines)


def _section_errors(dist: dict[str, int], total: int) -> str:
    if not dist:
        return "## 二、错误分布\n\n无失败样本。"
    rows = [
        [cat, str(cnt), _fmt_ratio(cnt / total if total else None)]
        for cat, cnt in sorted(dist.items(), key=lambda kv: -kv[1])
    ]
    return "## 二、错误分布\n\n" + _table(["error_category", "count", "占比"], rows)


def _section_buckets(title: str, buckets: Sequence[BucketStat]) -> str:
    if not buckets:
        return f"## {title}\n\n无数据。"
    rows = [
        [
            b.bucket,
            str(b.n),
            f"{b.ok_count}/{b.n}",
            _fmt_ratio(b.ok_rate),
            _fmt_ms(b.mean_wall_ms),
            _fmt_num(b.mean_url_count, 2),
            _fmt_ratio(b.refusal_rate),
            _fmt_ratio(b.short_response_rate),
        ]
        for b in buckets
    ]
    return f"## {title}\n\n" + _table(
        ["bucket", "n", "ok", "ok_rate", "mean_wall", "mean_urls", "refusal_rate", "short_rate"],
        rows,
    )


def _section_tokens(stats: dict[str, dict[str, Any]]) -> str:
    rows = []
    for axis in ("input", "output", "total"):
        d = stats.get(axis, {})
        rows.append([
            axis,
            str(d.get("n", 0)),
            str(d.get("sum", 0)),
            _fmt_num(d.get("mean"), 0) if d.get("mean") is not None else "-",
            _fmt_num(d.get("p50"), 0) if d.get("p50") is not None else "-",
            _fmt_num(d.get("p95"), 0) if d.get("p95") is not None else "-",
        ])
    return "## 四、token 消耗\n\n" + _table(
        ["axis", "n", "sum", "mean", "p50", "p95"], rows
    )


def _section_search(dist: dict[str, Any]) -> str:
    if not dist.get("n"):
        return "## 五、google_web_search 调用分布\n\n无数据。"
    hist = dist.get("histogram") or {}
    hist_rows = [[str(k), str(v)] for k, v in hist.items()]
    summary_line = (
        f"- 样本数：{dist['n']}  mean={_fmt_num(dist.get('mean'), 2)}  "
        f"p50={_fmt_num(dist.get('p50'), 2)}  p95={_fmt_num(dist.get('p95'), 2)}"
    )
    hist_md = _table(["calls_per_query", "count"], hist_rows) if hist_rows else "(空)"
    return "## 五、google_web_search 调用分布\n\n" + summary_line + "\n\n" + hist_md


def _section_models(dist: dict[str, int]) -> str:
    if not dist:
        return "## 六、model_used 分布\n\n无 ok 样本。"
    total = sum(dist.values())
    rows = [
        [m, str(c), _fmt_ratio(c / total if total else None)]
        for m, c in sorted(dist.items(), key=lambda kv: -kv[1])
    ]
    return "## 六、model_used 分布\n\n" + _table(["model", "count", "占比"], rows)


def _section_llm_scores(stats: dict[str, Any]) -> str:
    if not stats.get("n"):
        return (
            "## 七、LLM 裁判分数\n\n"
            "本次未启用 LLM 裁判，或未成功评分任何样本。"
        )
    overall = stats["overall"]
    rel = overall["relevance"]
    cit = overall["citation_quality"]
    lines = [
        "## 七、LLM 裁判分数",
        "",
        f"裁判样本数：{stats['n']}",
        "",
        "### 总体",
        "",
        _table(
            ["axis", "mean", "p50", "p95"],
            [
                ["relevance", _fmt_num(rel.get("mean"), 2), _fmt_num(rel.get("p50"), 1),
                 _fmt_num(rel.get("p95"), 1)],
                ["citation_quality", _fmt_num(cit.get("mean"), 2),
                 _fmt_num(cit.get("p50"), 1), _fmt_num(cit.get("p95"), 1)],
                ["hallucination_rate",
                 _fmt_ratio(overall.get("hallucination_rate")), "-", "-"],
            ],
        ),
    ]
    by_ts = stats.get("by_time_sensitivity") or {}
    if by_ts:
        lines += ["", "### 按 time_sensitivity 分层"]
        cross_rows = []
        for ts in sorted(by_ts.keys()):
            b = by_ts[ts]
            cross_rows.append([
                ts,
                str(b["n"]),
                _fmt_num(b["relevance"]["mean"], 2),
                _fmt_num(b["citation_quality"]["mean"], 2),
                _fmt_ratio(b["hallucination_rate"]),
            ])
        lines += [
            "",
            _table(
                ["bucket", "n", "relevance.mean", "citation.mean", "hallucination_rate"],
                cross_rows,
            ),
        ]
    return "\n".join(lines)


def _section_warnings(rows: Sequence[dict]) -> str:
    """Edge-case highlights to draw human eyes to suspicious samples."""
    slow = top_slow(rows, n=5)
    zero_urls = zero_url_ok_rows(rows)
    refusals = refusal_ok_rows(rows)

    out = ["## 八、异常样本提示"]

    if slow:
        out += [
            "",
            "### 最慢 5 条（ok 样本）",
            "",
            _table(
                ["id", "wall_ms", "model_used", "time_sensitivity", "domain"],
                [
                    [r["id"], _fmt_ms(r.get("wall_ms")), str(r.get("model_used") or "-"),
                     str(r.get("time_sensitivity") or "-"),
                     str(r.get("domain") or "-")]
                    for r in slow
                ],
            ),
        ]

    if zero_urls:
        out += [
            "",
            f"### 零 URL 的 ok 样本（{len(zero_urls)} 条）",
            "",
            _table(
                ["id", "time_sensitivity", "domain", "response_len"],
                [
                    [r["id"], str(r.get("time_sensitivity") or "-"),
                     str(r.get("domain") or "-"), str(r.get("response_len", 0))]
                    for r in zero_urls[:10]
                ],
            ),
        ]

    if refusals:
        out += [
            "",
            f"### 触发 refusal 启发式的 ok 样本（{len(refusals)} 条）",
            "",
            _table(
                ["id", "time_sensitivity", "domain", "model_used"],
                [
                    [r["id"], str(r.get("time_sensitivity") or "-"),
                     str(r.get("domain") or "-"), str(r.get("model_used") or "-")]
                    for r in refusals[:10]
                ],
            ),
        ]

    if len(out) == 1:  # no warnings at all
        out.append("\n无值得关注的异常样本。")
    return "\n".join(out)


# ---------- top-level render ----------


def render_summary(
    rows: Sequence[dict],
    scores: Sequence[dict],
    rows_by_id: dict[str, dict] | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """Render the full `summary.md` as a single string.

    `rows`       — heuristics rows (all envelopes).
    `scores`     — llm_scores rows (≤ 50 or empty).
    `rows_by_id` — for LLM stats cross-tab. Defaults to {r["id"]: r for r in rows}.
    `meta`       — optional dict with keys like generated_at / run_dir for the header.
    """
    meta = meta or {}
    rows_by_id = rows_by_id or {r["id"]: r for r in rows if "id" in r}

    st = overall_stats(rows)
    err_dist = error_category_distribution(rows)
    ts_buckets = bucket_stats(rows, "time_sensitivity")
    dom_buckets = bucket_stats(rows, "domain")
    diff_buckets = bucket_stats(rows, "difficulty")
    tok = token_stats(rows)
    search = search_call_distribution(rows)
    models = model_used_distribution(rows)
    llm = llm_score_stats(scores, rows_by_id)

    parts = [
        "# Research-mode 评测报告",
        "",
        _section_overview(st, meta),
        "",
        _section_errors(err_dist, st.total),
        "",
        _section_buckets("三、按 time_sensitivity 分层", ts_buckets),
        "",
        _section_buckets("三、按 domain 分层", dom_buckets),
        "",
        _section_buckets("三、按 difficulty 分层", diff_buckets),
        "",
        _section_tokens(tok),
        "",
        _section_search(search),
        "",
        _section_models(models),
        "",
        _section_llm_scores(llm),
        "",
        _section_warnings(rows),
        "",
    ]
    return "\n".join(parts)
