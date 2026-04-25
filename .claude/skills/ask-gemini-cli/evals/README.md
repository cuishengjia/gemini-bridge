# ask-gemini-cli — Research Mode 评测框架

评估 `ask-gemini --mode research` 的**执行效率**（成功率、fallback 率、延迟、token 开销）与**回答质量**（相关性、引用质量、幻觉率）。

## 目录结构

```
evals/
├── README.md                    # 本文件
├── datasets/
│   └── research_200.jsonl       # 200 条测试 query（锁定数据集）
├── runner.py                    # 批调用 bin/ask-gemini，落地 envelope
├── judge.py                     # 启发式全量 + LLM-judge 抽 50 条打分
├── analyze.py                   # 聚合指标 + 生成 summary.md
└── results/
    └── run-<YYYYMMDD-HHMMSS>/
        ├── envelopes/<id>.json  # 每条 query 的原始 envelope
        ├── heuristics.jsonl     # 每条的启发式打分
        ├── llm_scores.jsonl     # 抽样 50 条的 LLM-judge 打分
        └── summary.md           # 最终报告
```

## 数据集设计（锁定配比）

### 主轴：时效性（200 = 80+60+40+20）

| 桶 | 数量 | 定义 | 意图 |
|---|---:|---|---|
| `strong` | 80 | 近 30 天必须实时检索的事实 | 考验实时联网能力 |
| `medium` | 60 | 近 1 年内的更新知识 | 考验"新过训练截止日"的覆盖 |
| `evergreen_obscure` | 40 | 时间不敏感但冷门，模型参数里大概率没有 | 考验"真的去搜了" |
| `evergreen_common` | 20 | 基准组，不搜也能答对 | 检测"过度搜索"与事实稳定性 |

### 次轴：领域（打标签，不卡配额）

5 类：`tech`（科技/编程）、`news_finance`（时事/金融/政策）、`science`（科学/医学）、`lifestyle`（生活/产品/文化）、`sports_people`（体育/人物）。

### 难度标签

1 = 单跳（一次搜索就能答）、2 = 多跳（需要串联来源）、3 = 反直觉/争议（需要比较多源）。

### Query schema（`datasets/research_200.jsonl` 每行）

```json
{
  "id": "q001",
  "query": "What is the current stable version of Python as of 2026-04?",
  "time_sensitivity": "strong",
  "domain": "tech",
  "difficulty": 1,
  "notes": "最新小版本号可能月度变化"
}
```

## Runner 策略

- **并发**：2（OAuth 下安全档位，比串行快 ~2x，大概率不触发 429）
- **超时**：单次 wall 120s（上游 fallback 链自身已最多 300s，这里做快失败）
- **重试**：失败后重试 1 次，仍失败则记录 `ok:false`
- **断点续跑**：`results/run-<ts>/envelopes/<id>.json` 存在则 skip

## Judge 策略

- **启发式全量 200**（零成本）：`ok` 率、response 长度、URL 数、拒答词命中、`google_web_search` 触发率
- **LLM-judge 抽样 50**（分层：strong 20 / medium 15 / evergreen_obscure 10 / evergreen_common 5）：
  - 相关性（1–5）：回答是否切题
  - 引用质量（1–5）：是否含可靠 URL、URL 是否与答案一致
  - 幻觉（0/1）：是否有明显编造的事实

## 使用（建议顺序）

```bash
cd .claude/skills/ask-gemini-cli

# 1. 健康检查（确认 ask-gemini 可跑、OAuth 有效）
./bin/ask-gemini --mode research --query "what year is it?"

# 2. 先跑 pilot 20（每桶按比例 8/6/4/2，~8 分钟）
python3 evals/runner.py --dataset evals/datasets/research_200.jsonl \
  --sample-pilot 20 --concurrency 2 --timeout 120

# 3. 复盘 pilot 后跑剩余 180
python3 evals/runner.py --dataset evals/datasets/research_200.jsonl \
  --run-dir results/run-<ts> --concurrency 2 --timeout 120

# 4. 启发式打分 + LLM-judge 抽样 50
python3 evals/judge.py --run-dir results/run-<ts>

# 5. 生成报告
python3 evals/analyze.py --run-dir results/run-<ts>
```

## 成本估计

基于第四轮活调用数据：平均 ~38s/次、~56k token/次。

| 阶段 | 次数 | 预计时长（并发 2） | token |
|---|---:|---:|---:|
| Pilot | 20 | ~8 min | ~1.1M |
| 剩余 | 180 | ~60 min | ~10M |
| **合计** | **200** | **~70 min** | **~11M** |

## 评估指标（analyze.py 输出）

**执行效率**：
- `ok_rate`、`fallback_rate`、`timeout_rate`
- `wall_ms` P50 / P95 / max
- `total_tokens` P50 / P95
- `tool_calls` 中 `google_web_search` 占比

**回答质量**（启发式）：
- `url_rate`：回答含至少 1 个 URL 的比例
- `refusal_rate`：回答含"我不知道"/"I don't know"/"cannot find" 的比例
- `short_response_rate`：response < 100 字符的比例

**回答质量**（LLM-judge，n=50）：
- 相关性均值 / 分布
- 引用质量均值 / 分布
- 幻觉率

所有指标按 `time_sensitivity`、`domain`、`difficulty` 三维分层报告。
