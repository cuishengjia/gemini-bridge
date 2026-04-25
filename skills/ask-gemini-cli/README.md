# ask-gemini-cli

把 Claude Code 桥接到外部 `gemini` CLI 的只读 Skill。为 Claude 提供四项本身不具备的能力：

1. **analyze** — 1M+ token 的大上下文代码库分析
2. **research** — 基于 Google Search 实时检索、带 URL 引用的研究
3. **second-opinion** — 异源模型盲审独立评审
4. **multimodal** — 图片 / PDF / 视频帧分析

> 本文件面向**安装与运维**。Claude 自己如何调用，见 `SKILL.md`。设计决策与不变量见 `../../docs/implementation-plan.md` 与 `CLAUDE.md`。

---

## 1. 快速上手（3 分钟）

```bash
# 1. 安装 Gemini CLI（如尚未安装）
npm install -g @google/gemini-cli
#    或 Homebrew：brew install gemini-cli

# 2. 鉴权（任选其一）
gemini auth login                           # OAuth（推荐）
# 或
export GEMINI_API_KEY="sk-..."              # API Key

# 3. 冒烟验证（在本 skill 目录下执行）
./bin/ask-gemini --mode research --query "what is 2+2? one sentence."
# 期望 stdout：一行 JSON，形如 {"ok": true, "mode": "research", ...}
```

如这一步输出 `ok: true`，skill 即可用。任何失败都请对照 §7 故障矩阵定位。

---

## 2. 依赖与版本

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Gemini CLI | ≥ 0.40.0 | 必须支持 `--approval-mode plan`、`--policy`、`-o stream-json` |
| Python | ≥ 3.9 | wrapper 只用标准库，不需要 pip 依赖 |
| pytest | 仅跑测试需要 | `python3 -m pip install pytest pytest-cov` |

**Gemini CLI 位置**：wrapper 默认读 `/opt/homebrew/bin/gemini`（macOS + Homebrew Apple Silicon）。其它环境必须设置环境变量：

```bash
export GEMINI_BIN=/usr/local/bin/gemini        # Linux / Intel Mac
export GEMINI_BIN=$HOME/.local/bin/gemini      # npm 全局装在用户目录
```

可用 `which gemini` 定位实际路径。

---

## 3. 鉴权

支持两种方式，优先级：环境变量 > OAuth 凭据文件。

### 3.1 OAuth（推荐，免费配额更高）

```bash
gemini auth login
```

完成后凭据写入 `~/.gemini/oauth_creds.json`。wrapper 启动时会检查此文件是否存在且非空。

### 3.2 API Key

```bash
export GEMINI_API_KEY="sk-..."
# 持久化：写入 ~/.zshrc / ~/.bashrc
```

### 3.3 `GOOGLE_CLOUD_PROJECT` 环境变量

**默认剥离**：wrapper 在子进程启动前清掉 `GOOGLE_CLOUD_PROJECT`，避免 Gemini 探测组织订阅导致挂起。如需保留（你确实使用 GCP 订阅）：

```bash
export ASK_GEMINI_KEEP_GCP=1
```

### 3.4 如何确认已鉴权

```bash
gemini auth status     # 会显示当前账号或提示未登录
ls ~/.gemini/oauth_creds.json 2>/dev/null && echo "OAuth OK"
echo ${GEMINI_API_KEY:+API_KEY_SET}
```

---

## 4. 四个 mode 的使用示例

所有调用都返回**单行 JSON envelope**。成功时 `ok: true`，失败时 `ok: false` + `error.kind`。完整 schema 见 `SKILL.md` §Envelope 与 `docs/envelope-schema.json`。

### 4.1 analyze — 大上下文代码库分析

```bash
./bin/ask-gemini \
  --mode analyze \
  --target-dir /abs/path/to/repo \
  --prompt "Map the data flow from HTTP ingress to the DB write path. List every intermediate layer with file:line." \
  --persist-to notes/data-flow.md
```

何时用：Claude 上下文塞不下整个仓库时。Gemini 通过 `read_file` / `glob` / `grep` 自行浏览目标目录。

### 4.2 research — Google 接地研究

```bash
./bin/ask-gemini \
  --mode research \
  --query "What changed in Next.js 15 App Router compared to 14? Link release notes." \
  --persist-to notes/nextjs-15.md
```

何时用：训练截止日期之后的事实、最新版本、近期新闻。envelope 的 `tool_calls` 会列出 Gemini 实际执行的 `google_web_search` / `web_fetch` 调用。

### 4.3 second-opinion — 盲审

```bash
./bin/ask-gemini \
  --mode second-opinion \
  --task "Users report pagination occasionally skips items when the dataset shrinks mid-session. Decide how to stabilize it." \
  --artefact-file design/pagination-proposal.md \
  --persist-to notes/pagination-review.md
```

**盲审不变量（必读）**：`--task` 只能描述**问题本身**。**绝不能**包含 Claude 的分析过程、倾向的结论、或推荐的方案——否则评审不独立，mode 价值归零。

- ✅ 好的 `--task`："用户反馈分页在数据集收缩时会跳项，需要决策如何稳定化。"
- ❌ 坏的 `--task`："我认为应该用 cursor-based pagination + snapshot isolation，请确认。"

### 4.4 multimodal — 图片 / PDF

```bash
# 图片
./bin/ask-gemini \
  --mode multimodal \
  --image screenshots/dashboard-bug.png \
  --prompt "Describe the UI issue visible in this screenshot. Where would you look in code to fix it?"

# PDF
./bin/ask-gemini \
  --mode multimodal \
  --pdf specs/protocol-v3.pdf \
  --prompt "Summarize §4 of the spec and list all MUST requirements."
```

`--image` 与 `--pdf` 互斥，必须且只能提供一个。

---

## 5. `--persist-to` 跨 session 缓存

所有四个 mode 都支持 `--persist-to <path>`。效果：

- Gemini 的 `response` 字段内容（原始文本）会同步写入该路径（`.md` 格式）
- envelope 的 `persisted_to` 字段会回显该绝对路径
- 下次会话里 Claude 可直接 `Read` 该文件，**无需重跑 Gemini**（省配额 + 省时间）

**推荐命名约定**（防止 Claude 跨项目查找时歧义）：

```
<repo>/docs/gemini-notes/<topic>.md
<repo>/docs/gemini-notes/analyze-<date>-<scope>.md
```

目录不存在时 wrapper 会自动创建（`parents=True`）。如目标路径已存在会**覆盖**——如需保留历史，调用前自行重命名。

---

## 6. 成本与配额

### 6.1 envelope 自带成本字段

每次调用的 stdout JSON 都包含：

```json
"stats": {
  "input_tokens": 87277,
  "output_tokens": 285,
  "cached_tokens": 0,
  "total_tokens": 89966
}
```

Claude 看到异常大的 `total_tokens`（比如 analyze 模式 >200k）应主动向用户汇报。

### 6.2 三级 fallback 对成本的影响

```
gemini-3-pro-preview    →  gemini-2.5-pro   →  gemini-2.5-flash
（300s 超时）              （180s 超时）        （120s 超时）
```

- **仅在** `quota_exhausted` / `timeout` / 瞬时 5xx 错误时才回退
- `auth` / `bad_input` / `config` 错误**不回退**（重试无意义）
- envelope 的 `attempts` 数组记录了每次尝试的 `model` + `exit_code` + `duration_ms`
- `fallback_triggered: true` 意味着前序模型失败并成功回退

`gemini-2.5-flash-lite` **刻意不在**回退链中：分析质量过低时宁可暴露配额耗尽，也不静默降级。

### 6.3 审计日志

所有调用追加到 `~/.cache/ask-gemini-cli/invocations.jsonl`（10 MB 滚动）。一行一个 envelope，可供事后对账 / 成本复盘。路径可用 `ASK_GEMINI_CACHE_DIR` 环境变量覆盖。

---

## 7. 故障矩阵

envelope 失败时 `error.kind` 的八种取值与处置：

| `error.kind` | 典型触发 | 处置 |
|---|---|---|
| `auth` | 未登录 / API Key 未设 / 已过期 | 按 §3 重新鉴权；**不要自动重试** |
| `bad_input` | wrapper 传给 Gemini 的参数被拒（我们的 bug） | 查看 `error.stderr_tail`；在本仓库提 issue |
| `quota_exhausted` | 三个模型全部返回 quota 错误 | 换账号 / 等配额 / 缩小 scope |
| `timeout` | 超过当前模型的超时阈值 | 缩小 `--target-dir` 或 `--prompt` 聚焦；必要时分批 |
| `config` | `trustedFolders.json`、policy 文件、sandbox flag 泄露 | 严格按 `error.setup_hint` 修 |
| `turn_limit` | Agent 触发内置 step cap | 拆小任务，或提示 Gemini "just answer, no further tool use" |
| `malformed_output` | stream-json 非预期格式 | 很可能 Gemini CLI 升级了协议——降级/固定 CLI 版本 |
| `general` | exit 1 未匹配任何模式 | 看 `error.stderr_tail` 原始错误；提 issue 并附上 |

### 7.1 常见陷阱

**陷阱 1：stdout 里出现了 prompt 原文回显**  
已于 v1 修复。若再次出现：检查 `lib/invoke.py::_parse_events` 是否还在按 `role in {assistant, model}` 过滤 content/delta。

**陷阱 2：`trustedFolders.json` 无效**  
该文件的值必须是**字符串**（`"TRUST_FOLDER"` / `"TRUST_PARENT"` / `"DO_NOT_TRUST"`），**不能**是 dict。Gemini 对 dict 是**静默拒绝**（不报错也不生效）。

**陷阱 3：`--approval-mode plan` 被覆盖**  
Wrapper 在构造 argv 时多层硬编码 + `_assert_safety` 双重校验。任何尝试注入 `--yolo` / `--sandbox` / `--approval-mode=auto` 的改动都会被启动前拒绝。

**陷阱 4：prompt 模板里的 `{name}` 被当成格式化占位符**  
Wrapper 不用 `str.format`，改用 sentinel 三遍替换的 `_render()`。新增模板里的 `{xxx}` 占位符时必须同步更新 `tests/test_brace_escape.py::ALLOWED_PLACEHOLDERS`。

### 7.2 冒烟验证

```bash
# 全量 mock 测试（无网络，无配额消耗）
python3 -m pytest -q

# 活调用（会消耗配额）
ASK_GEMINI_LIVE=1 bash tests/smoke_test.sh
```

---

## 8. 隐私与只读保证

### 8.1 只读机制（多层防御）

1. **硬编码 flag**：`invoke.build_argv` 强制 `--approval-mode plan` + `-o stream-json` + `--policy policies/readonly.toml`
2. **Policy whitelist**：只允许 `read_file` / `read_many_files` / `glob` / `grep` / `list_directory` / `google_web_search` / `web_fetch`；显式 deny `run_shell_command` / `write_file` / `edit` / `replace` / `save_memory`；MCP 全 deny
3. **启动前断言**：`_assert_safety` 再次核对 argv，拒绝任何被禁 flag（`--yolo` / `-s` / `--sandbox` / `--admin-policy` / `--allowed-tools` 等）
4. **GEMINI_BIN 白名单**：拒绝 `/tmp/`、`/var/tmp/`、`/dev/shm/` 等 world-writable 位置的二进制（防止恶意 binary 替换）；可用 `ASK_GEMINI_BIN_UNRESTRICTED=1` 显式覆盖
5. **`--target-dir` 黑名单**：拒绝 `/`、`/etc`、`/usr`、`$HOME` 等过宽路径作为 trust 范围，避免污染 `~/.gemini/trustedFolders.json`
6. **`--persist-to` symlink 防护**：拒绝跟随目标 symlink；`O_NOFOLLOW` 双重防御
7. **自动信任范围**：只对用户显式传入的 `--target-dir` 添加 `TRUST_FOLDER`；不会触达其他目录

### 8.1.1 second-opinion 模式的盲审约束（仅靠自觉）

`--task` 描述的应该是**要解决的问题**，**绝不能**包含 Claude 自己的推理过程或建议方案。这个模式的全部价值就是拿到一个独立异源的评审；泄露 Claude 的思维链等于自废武功。

wrapper 无法也不会自动检测这一点 —— 调用方（Claude 或人）必须自觉遵守。

### 8.2 发送给 Gemini 的数据

调用时 Gemini 会看到：

- 你的 prompt（`--prompt` / `--query` / `--task` + 模板）
- `--target-dir` 目录下、由 Gemini 主动 read 的文件内容
- `--artefact-file` 的完整内容（second-opinion 模式）
- `--image` / `--pdf` 的二进制内容（multimodal 模式）

**不会**发送：

- 仓库中未被 Gemini read 的文件
- 你的环境变量（除了 Gemini CLI 自身认证相关）
- Claude Code 的会话历史或推理链（需要你自己在 `--task` 里自律过滤）

### 8.3 审计日志可能包含敏感数据

`~/.cache/ask-gemini-cli/invocations.jsonl` 默认包含每次调用的完整 envelope（含 `response`、`tool_calls` 等）。文件权限是 `0o600`，目录是 `0o700`，但仍要注意：

- **敏感代码库分析**：`response` 字段会引用 / 摘录 Gemini 实际读到的代码
- **共享主机**：root 或同账号其他进程能读到日志
- **长期留存**：默认 10 MB 滚动一次（`invocations.1.jsonl`）

三档可选的隐私控制：

```bash
# 推荐：保留元数据（mode / model / 耗时 / 配额 / 错误），但不记录回答正文
export ASK_GEMINI_NO_LOG_RESPONSE=1

# 全关：完全跳过审计日志（损失调试能力）
export ASK_GEMINI_LOG_DISABLED=1

# 或一次性清理
rm -f ~/.cache/ask-gemini-cli/invocations.jsonl
```

`ASK_GEMINI_NO_LOG_RESPONSE=1` 只影响落盘的内容；调用方收到的 stdout envelope 不变。

---

## 9. 进阶配置

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `GEMINI_BIN` | `/opt/homebrew/bin/gemini` | Gemini CLI 可执行文件路径。**拒绝** `/tmp/`、`/var/tmp/`、`/dev/shm/` 等 world-writable 位置 |
| `ASK_GEMINI_BIN_UNRESTRICTED` | 未设 | 设为 `1` 跳过 `GEMINI_BIN` 路径白名单（仅在你完全确认来源时使用） |
| `GEMINI_API_KEY` | 无 | API Key（无 OAuth 时必需） |
| `ASK_GEMINI_KEEP_GCP` | 未设 | 保留 `GOOGLE_CLOUD_PROJECT` 环境变量 |
| `ASK_GEMINI_CACHE_DIR` | `~/.cache/ask-gemini-cli/` | 审计日志目录 |
| `ASK_GEMINI_NO_LOG_RESPONSE` | 未设 | 设为 `1` 让审计日志只记录元数据（不写 `response`、`tool_calls`） |
| `ASK_GEMINI_LOG_DISABLED` | 未设 | 设为 `1` 完全跳过审计日志 |
| `ASK_GEMINI_LIVE` | 未设 | `smoke_test.sh` 使用，`1` = 真实调用 |

---

## 10. 路线图与非目标

### v1 已冻结范围（当前）

- 4 个 mode：analyze / research / second-opinion / multimodal
- 三级 fallback：3-pro-preview → 2.5-pro → 2.5-flash
- Envelope Schema v1（字段冻结）
- 审计日志 10 MB 滚动
- OAuth + API Key 双鉴权

### 非目标（v1 不做，未来可能做）

- ❌ **写操作**：永不加。需要写就用 Claude 本体，不用这个 skill
- ❌ **流式对外**：wrapper 内部用 stream-json 解析，对外永远是同步一次性 envelope
- ❌ **MCP 桥接**：policy 层 MCP 全 deny，保持调用路径可预测
- ❌ **预算硬上限**：envelope 只暴露 `stats.total_tokens`，由调用方（Claude 或人）判断，不在 wrapper 里做中断

### v2 考虑项（未排期）

- 流式输出（用户要求）时的可选 NDJSON 模式
- `--target-files <glob>` 显式列文件，替代自动浏览
- 多轮 second-opinion（Gemini 对 Gemini 的互审）

---

## 附录：相关文档

- `SKILL.md` — Claude 调用契约（skill 规格本体）
- `MIGRATION.md` — project-local → user-global 迁移清单
- `docs/envelope-schema.json` — envelope v1 的 JSON Schema
- `docs/test-report.md` — 活调用冒烟结果 + 已知 bug 复盘
- `../../docs/implementation-plan.md` — 冻结的设计决策与理由
- `../../docs/gemini-cli-reference.md` — 精简的 Gemini CLI 官方参考
- `../../CLAUDE.md` — 开发本 skill 时的仓库指南
