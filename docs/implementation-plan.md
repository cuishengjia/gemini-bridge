# ask-gemini-cli 实施计划（v1，已锁定）

**决策冻结日期**：2026-04-19
**Skill 名**：`ask-gemini-cli`
**开发位置**：`<repo-root>/.claude/skills/ask-gemini-cli/`
**迁移目标**：`~/.claude/skills/ask-gemini-cli/`（稳定后）
**预估工作量**：2–3 工程日
**参考资料**：`docs/gemini-cli-reference.md`

---

## 1. 最终 scope：四模式 + 跨模式参数

### 1.1 四种工作模式

| 模式 | 独特价值 | 关键输入 |
|---|---|---|
| `analyze` | 超长上下文代码分析（1M+ tokens） | `--target-dir`, `--prompt` |
| `research` | **Google 原生搜索接地**（稀缺能力） | `--query`, 可选 `--target-dir` |
| `second-opinion` | 独立模型视角盲审 | `--task`, `--artefact-file`（**不给 Claude 推理链**） |
| `multimodal` | 图片 / PDF / 视频分析 | `--image` 或 `--pdf`, `--prompt` |

### 1.2 跨模式共享

- `--persist-to <path>`：把 `.response` 同时落地为 `.md` 文件，Claude 后续可 `Read` 复用，实现**跨 session 缓存**。

---

## 2. 七问最终决定

| # | 问题 | 决定 | 实现要点 |
|---|---|---|---|
| Q1 | 预算硬中止 | **不做** | 只在信封返回 `stats.total_tokens`，Claude 自己判断 |
| Q2 | Second-opinion 盲度 | **严格盲审** | prompt 模板仅含 `{task}` + `{artefact}`；SKILL.md 明确禁止 Claude 把推理链写进 `--task` |
| Q3 | 返回格式 | **结构化信封 v1**（见 §4） | 含 `ok/mode/model_used/fallback_triggered/attempts/response/stats/tool_calls/persisted_to/warnings/error` |
| Q4 | 流式 | **对外同步** | wrapper 内部用 `-o stream-json` 解析 `tool_use` 事件填信封的 `tool_calls` 字段 |
| Q5 | Policy TOML | **附 `policies/readonly.toml`** | 通过 `--policy` 传入，只读白名单 + 禁 MCP |
| Q6 | 自动信任 | **自动信任 target_dir**（用户接受风险） | + 审计日志落盘 |
| Q7 | 日志路径 | **`~/.cache/ask-gemini-cli/invocations.jsonl`** | 10MB 滚动 |

---

## 3. 目录结构

```
.claude/skills/ask-gemini-cli/
├── SKILL.md                         # Claude Code 自动发现 + 触发描述
├── README.md                        # 用户文档：setup / auth / 故障排查
├── MIGRATION.md                     # 迁移到 ~/.claude/skills/ 检查清单
├── bin/
│   └── ask-gemini                   # 可执行入口（Python 3 shebang）
├── lib/
│   ├── __init__.py
│   ├── invoke.py                    # 构建 argv、spawn gemini、流式解析 stream-json
│   ├── fallback.py                  # 模型 fallback 状态机
│   ├── exit_codes.py                # exit_code + stderr → ErrorKind 分类器
│   ├── envelope.py                  # 信封构造（成功/失败）
│   ├── preflight.py                 # 认证检测 + 信任检测 + 自动信任 + 审计
│   └── persist.py                   # --persist-to 落地逻辑
├── policies/
│   └── readonly.toml                # Gemini Policy Engine 白名单
├── prompts/
│   ├── analyze.md                   # 大上下文分析模板
│   ├── research.md                  # 强制 "Use google_web_search" 的研究模板
│   ├── second_opinion.md            # 盲审模板（仅 task + artefact）
│   └── multimodal.md                # 多模态模板
├── examples/
│   ├── analyze-repo.json            # 录制的成功信封
│   ├── research-query.json
│   ├── second-opinion.json
│   └── multimodal-screenshot.json
└── tests/
    ├── __init__.py
    ├── test_exit_codes.py           # 分类器单元测试
    ├── test_fallback.py             # 状态机单元测试（monkeypatch invoke.run）
    ├── test_envelope.py             # 信封 schema 契约
    ├── test_persist.py
    ├── contract_test.py             # 用录制 fixture 验契约
    ├── fixtures/
    │   ├── gemini_ok_analyze.jsonl           # stream-json 录制
    │   ├── gemini_ok_research_with_search.jsonl
    │   ├── gemini_auth_fail.txt              # stderr 样本
    │   ├── gemini_quota_exhausted.txt
    │   └── ...
    └── smoke_test.sh                # 门控：ASK_GEMINI_LIVE=1 才跑
```

**外部 runtime 产物**（不在 skill 目录）：
- `~/.cache/ask-gemini-cli/invocations.jsonl`
- `~/.cache/ask-gemini-cli/invocations.1.jsonl`（滚动旧日志）

---

## 4. 信封 Schema v1（冻结）

### 4.1 成功
```json
{
  "ok": true,
  "mode": "analyze | research | second-opinion | multimodal",
  "model_used": "gemini-3-pro-preview",
  "fallback_triggered": false,
  "attempts": [
    {"model": "gemini-3-pro-preview", "exit_code": 0, "duration_ms": 14200}
  ],
  "response": "<Gemini .response 原文>",
  "stats": {
    "input_tokens": 125430,
    "output_tokens": 2100,
    "cached_tokens": 8000,
    "total_tokens": 127530
  },
  "tool_calls": [
    {"name": "google_web_search", "query": "current Node.js stable version"}
  ],
  "persisted_to": "/path/to/file.md" | null,
  "warnings": ["target dir auto-trusted for first use"]
}
```

### 4.2 失败
```json
{
  "ok": false,
  "mode": "...",
  "error": {
    "kind": "auth | bad_input | quota_exhausted | timeout | config | turn_limit | malformed_output | general",
    "message": "<human-readable summary>",
    "setup_hint": "<actionable next step>",
    "exit_code": 41,
    "stderr_tail": "<last 40 lines>"
  },
  "attempts": [...]
}
```

### 4.3 契约保证
- 字段名/层级冻结 v1，任何改动算 breaking
- 未出现的字段保留为 `null` 或空列表，**永不省略**
- `docs/envelope-schema.json` 作为 JSON Schema 落地，`contract_test.py` 用其验证

---

## 5. 模型 fallback 链（wrapper 自管）

```
FALLBACK_CHAIN = [
    "gemini-3-pro-preview",   # 首选：最强 + 1M 上下文
    "gemini-2.5-pro",         # preview 配额耗尽 fallback
    "gemini-2.5-flash",       # 都耗尽才降速
]
# flash-lite 不在链内：推理能力不足以做分析/第二意见
```

**状态机**（`lib/fallback.py`）：
- `exit_code == 0` + 可解析 → 成功返回
- `exit_code == 0` + 解析失败 → `kind=malformed_output`，**不降级**
- `exit_code == 1` + stderr 匹配 `/quota|rate limit|RESOURCE_EXHAUSTED|429/i` → **降级**重试
- `exit_code == 1` + stderr 匹配 `/500|503|UNAVAILABLE|DEADLINE_EXCEEDED/i` → 降级重试（每模型最多 1 次）
- `exit_code == 1` 其他 → **不降级**
- `41 auth` → `kind=auth`，不降级
- `42 bad_input` → `kind=bad_input`，不降级
- `44 sandbox` → `kind=config`（我们不用 `-s`，出现即配置错）
- `52 config` → `kind=config`
- `53 turn_limit` → `kind=turn_limit`
- Python subprocess timeout → 降级一次后 `kind=timeout`
- 链耗尽 → `kind=quota_exhausted`，`attempts` 列出所有尝试

**超时设置**（按模型阶梯）：
- `gemini-3-pro-preview`: 300s
- `gemini-2.5-pro`: 180s
- `gemini-2.5-flash`: 120s

---

## 6. 固定调用模板

```bash
/opt/homebrew/bin/gemini \
  --approval-mode plan \                          # 硬编码，不可覆盖
  -m <current_model_from_chain> \
  -o stream-json \                                # 内部流式，方便抓 tool_calls
  --policy <SKILL_DIR>/policies/readonly.toml \   # 深度防御
  [--include-directories <target_dir>] \          # 按模式决定
  -p <composed_prompt>                            # 从 prompts/*.md 模板合成
```

**环境变量处理**：
- `GEMINI_API_KEY` 透传
- `GOOGLE_CLOUD_PROJECT` 默认 **剥离**（触发组织订阅检查会坑），除非用户显式 `--vertex`

---

## 7. Policy TOML（只读白名单）

**`policies/readonly.toml`**：
```toml
# 允许：只读 + 搜索
[[rule]]
toolName = ["read_file", "read_many_files", "glob", "grep", "list_directory", "google_web_search", "web_fetch"]
decision = "allow"
priority = 100

# 拒绝：所有写操作和 shell
[[rule]]
toolName = ["run_shell_command", "write_file", "edit", "replace", "save_memory"]
decision = "deny"
priority = 500
denyMessage = "ask-gemini-cli runs Gemini strictly read-only."

# 拒绝：任何 MCP 工具
[[rule]]
mcpName = "*"
decision = "deny"
priority = 400
denyMessage = "MCP tools disabled in ask-gemini-cli."
```

---

## 8. 阶段推进顺序（依赖图 + 估时）

```
1. 骨架           (≤0.5h)  ─┐
2. SKILL.md       (1–2h)   ─┤
3. wrapper 核心   (3–4h)   ─┼── 5. 安全/策略     (1–2h)
                            ├── 6. 认证 UX       (2–3h)
                            └── 4. fallback     (3–4h)
                                  └── 7. envelope+日志 (2–3h)
                                        └── 8. 测试    (4–6h)
                                              └── 9. 文档  (1–2h)
                                                    └── 10. 迁移  (1h + 审计)
```

5 / 6 可与 4 并行。

**总估时**：~2–3 工程日。

---

## 9. 各阶段文件清单

### Phase 1 — 骨架
创建目录树 + 空占位文件 + `.gitignore`（`__pycache__/`, `*.pyc`，日志在外部不需排除）。

### Phase 2 — SKILL.md
```yaml
---
name: ask-gemini-cli
description: >
  Delegate to Google's Gemini CLI for four cases Claude Code cannot easily do alone:
  (1) large-context codebase analysis (1M+ token window);
  (2) Google-search-grounded research with URL citations for up-to-date information;
  (3) blind independent second opinion on plans or code;
  (4) multimodal analysis of images / PDFs / video frames.
  Gemini runs strictly read-only (approval-mode=plan + policy whitelist) and cannot
  edit files or run shell. Use when the task is analytical and Claude needs either
  more context, fresh web info, an independent critic, or visual understanding.
---
```
Body 含：何时调用、四种调用模板、信封字段说明、Claude 侧守则（不改 approval-mode、不泄 Claude 推理链给 second-opinion、信封 `error.kind` 的处理指南）。

### Phase 3 — Wrapper 核心
- `bin/ask-gemini`：argparse 分发
- `lib/invoke.py`：构建 argv（锁 `--approval-mode plan`、`-o stream-json`、`--policy`），spawn subprocess，流式解析 JSONL 事件
- 四个 `prompts/*.md` 模板

### Phase 4 — Fallback + Exit codes
- `lib/exit_codes.py`：纯函数分类器（表驱动）
- `lib/fallback.py`：状态机，调 `invoke.run()`

### Phase 5 — 安全/Policy
- `lib/invoke.py` 硬断言 `--approval-mode plan` 和 `-o stream-json`（wrapper CLI 不暴露覆盖选项）
- `policies/readonly.toml`

### Phase 6 — 认证 UX
- `lib/preflight.py`：
  - 检查 `/opt/homebrew/bin/gemini` 可执行
  - 检查 `GEMINI_API_KEY` 或 OAuth 缓存
  - 检查 target_dir 是否在 `~/.gemini/trustedFolders.json` 中
  - 若不在：**自动 `gemini folders trust <dir>`**（Q6 决定），落审计日志 `{"event": "auto_trusted", ...}`
  - 若 `GOOGLE_CLOUD_PROJECT` 与 `GEMINI_API_KEY` 同时存在 → 警告

### Phase 7 — 信封 + 日志
- `lib/envelope.py`：`build_success()` / `build_error()`
- `lib/persist.py`：`--persist-to` 落 `.md`
- `bin/ask-gemini`：每次调用完整信封落 `~/.cache/ask-gemini-cli/invocations.jsonl`
- `docs/envelope-schema.json`

### Phase 8 — 测试
- 离线 unit：`test_exit_codes.py` / `test_fallback.py`（monkeypatch）/ `test_envelope.py` / `test_persist.py`
- 契约：`contract_test.py` 用 JSON Schema 验信封
- 录制 fixture（每模式至少 1 个成功 + 1 个失败）
- `smoke_test.sh`：`ASK_GEMINI_LIVE=1` 才跑真 gemini 一次性验证四模式
- 覆盖率目标 `lib/` ≥ 80%

### Phase 9 — 文档
- `README.md`：setup（API key 优先）、四种调用模板、troubleshooting 表（每个 `error.kind` 一行）、成本提示
- 完善 `SKILL.md` 描述措辞（根据初期真实使用迭代）

### Phase 10 — 迁移
- `MIGRATION.md` 检查清单
- **Wrapper 路径审计**：全部 `Path(__file__).resolve().parent` 派生，**无硬编码 `GeminiCLI4CC`**

---

## 10. 风险汇总

| 风险 | 等级 | 缓解 |
|---|---|---|
| Fallback 状态机误分类（stderr regex 脆） | **HIGH** | `test_fallback.py` 用 fake stderr 穷举；正则保守起手 |
| 硬编码项目路径破坏迁移 | **HIGH** | Phase 10 专门审计；单一规则 `Path(__file__).resolve().parent` |
| SKILL.md 措辞让 Claude 挑不准 skill | **MEDIUM** | 初期真实使用观察，Phase 9 二次迭代 |
| Gemini v0.40 nightly，JSON / flag 变动 | **MEDIUM** | 契约测试 + 版本固定在 README；信封里访问字段用 `.get()` 防御 |
| 恶意 GEMINI.md 提示注入（Q6 接受的风险） | **用户已接受** | 审计日志记录 auto-trust；不额外代码层缓解 |
| Token 成本失控 | **LOW-MEDIUM** | 信封回 `stats.total_tokens`；README 建议 `.geminiignore` 模板 |
| Multimodal 模型兼容性（flash 不支持图片？） | **MEDIUM** | Phase 3 单独冒烟验证各模型 multimodal 支持；必要时给 multimodal 单独 fallback 链 |

---

## 11. 成功验收

- `bin/ask-gemini --mode analyze --target-dir <dir> --prompt "..."` 返回合法信封 `ok:true` + 非空 `response`
- `research` 模式信封 `tool_calls` 含至少一条 `google_web_search`
- 强制 `gemini-3-pro-preview` 配额错误 → 信封 `fallback_triggered:true`，`model_used:"gemini-2.5-pro"` 或 `"gemini-2.5-flash"`
- Gemini 在任何测试中都未写入文件（smoke 用只读 target_dir 对照检查）
- 离线测试套件 `lib/` 覆盖率 ≥ 80%，不触发真 gemini 调用
- Claude Code 用 "帮我评审这个方案" 能稳定自动挑中本 skill（观察 ≥5 次真实会话）
- 按 `MIGRATION.md` 迁移到 `~/.claude/skills/` 后，在项目外的 cwd 仍能正常跑四模式

---

## 12. 不在 v1 的东西（已决议延后）

- `--stream` 对外流式（Q4 A）
- `--budget-tokens` 硬中止（Q1 A）
- `second-opinion` 给 Claude 推理链选项（Q2 A）
- Gemini extensions / skills / hooks 子命令联动
- 多模态单独的 fallback 链（待 Phase 3 实测决定）
