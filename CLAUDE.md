# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库定位

本仓库是 Claude Code plugin **`gemini-bridge`** 的源代码仓库。该 plugin 把 Claude Code 桥接到外部 `gemini` CLI，以 4 个独立 skill 暴露 4 项**只读**能力（这些是 Claude 本身无法胜任的）：

1. **`gemini-bridge:analyze`** — 1M+ token 级别的大上下文代码库分析
2. **`gemini-bridge:research`** — 基于 Google Search 实时检索、带 URL 引用的研究
3. **`gemini-bridge:second-opinion`** — 让异源模型做**盲审**独立评审
4. **`gemini-bridge:multimodal`** — 图像 / PDF / 视频帧分析

仓库根**就是** plugin 根。4 个 skill 共享同一个后端（`bin/ask-gemini --mode <X>`），无代码重复。

## 仓库布局（v1.1.0 后）

```
gemini-bridge/
├── .claude-plugin/{plugin,marketplace}.json   # plugin metadata
├── skills/                                    # 4 个 thin SKILL.md (描述 + 调用 bin/ask-gemini)
│   ├── analyze/SKILL.md
│   ├── research/SKILL.md
│   ├── second-opinion/SKILL.md
│   └── multimodal/SKILL.md
├── bin/ask-gemini                             # 唯一入口（Python 脚本，无 .py 后缀）
├── lib/                                       # invoke / fallback / preflight / envelope / persist / audit_log / exit_codes
├── prompts/                                   # 每个 mode 一个 .md 模板
├── policies/readonly.toml                     # 硬编码 allow/deny 规则，通过 gemini --policy 传入
├── tests/                                     # pytest 套件（220 用例） + smoke_test.sh（活调用，需开关）
├── examples/                                  # 四个 mode 各一份抓取的 envelope
├── evals/                                     # research 模式 200 条评测 harness + 结果（results/ 不入库）
├── docs/                                      # 用户手册 + 设计文档 + envelope schema + 测试报告
├── CLAUDE.md / LICENSE / README.md
└── .gitignore
```

## 常用命令

以下命令默认 `cwd = <repo root>`。仓库没有 `pyproject.toml` / `conftest.py` —— 测试文件自己往 `sys.path` 注入路径，所以直接在仓库根跑 `python3 -m pytest tests/` 即可。

```bash
# 全量测试（全部 mock，不调真实网络）。目标：220 用例 ~0.2s 通过。
python3 -m pytest tests/ -q

# 单文件 / 单用例
python3 -m pytest tests/test_invoke.py -q
python3 -m pytest tests/test_invoke.py::test_parse_events_filters_user_role_echo_from_response -q

# 覆盖率
python3 -m pytest tests/ --cov=lib --cov-report=term-missing

# Lint（无 ruff 配置文件，使用 ruff 默认规则）
ruff check lib bin tests

# 活调用冒烟（真实调 Gemini，消耗配额，默认关闭）
ASK_GEMINI_LIVE=1 bash tests/smoke_test.sh

# 单次活调用（任一 mode）
./bin/ask-gemini --mode research --query "what is 2+2? one sentence."
```

`bin/ask-gemini` **没有 `.py` 后缀**。测试里要 import 它，必须用 `importlib.machinery.SourceFileLoader("ask_gemini_cli", str(BIN_PATH))` 这种写法 —— 参考 `tests/test_brace_escape.py`。

## 架构主线 —— 单次调用的流水线

一次 `bin/ask-gemini` 调用严格按如下顺序流过每一层，每层都是独立模块以便单独 mock：

```
argparse → _validate → _compose（prompt 模板渲染）
       → preflight.run_preflight     （auth / binary / 路径 / auto-trust）
       → fallback.run_with_fallback
             └─ invoke.build_argv + invoke.run（subprocess + stream-json 解析）
       → persist.persist_response    （可选，当传了 --persist-to）
       → envelope.build_success / build_error（Schema v1，已冻结）
       → audit_log.append            （JSONL 轮转，位于 ~/.cache/ask-gemini-cli/）
       → stdout：始终一行 JSON
```

### 核心不变量（多层防御，代码多处重复校验）

- **只读强制**：`invoke.build_argv` 硬编码 `--approval-mode plan`、`-o stream-json`、`--policy policies/readonly.toml`。`_assert_safety` 在启动子进程前再次核对 argv，拒绝任何被禁标志（`--yolo`、`-s`、`--sandbox`、`--approval-mode=auto`、`--admin-policy`、`--allowed-tools` 等）。
- **三级回退链**（`lib/fallback.py`）：`gemini-3-pro-preview`（300s）→ `gemini-2.5-pro`（180s）→ `gemini-2.5-flash`（120s）。**仅**在 quota / 瞬时错误时触发回退，auth / bad_input / config 类错误一律不回退。
- **Envelope Schema v1 已冻结**。对外契约字段为 `ok`、`mode`、`model_used`、`fallback_triggered`、`attempts`、`response`、`stats`、`tool_calls`、`persisted_to`、`warnings`、`error`。任何改动都是破坏性变更。Schema 见 `docs/envelope-schema.json`。
- **错误分类**（`lib/exit_codes.py`）：gemini 的退出码 + stderr 模式映射到以下之一：`{auth, bad_input, quota_exhausted, timeout, config, turn_limit, malformed_output, general}`。只有 `quota_exhausted` 和 `timeout` 会触发回退。
- **GEMINI_BIN 路径白名单**：拒绝 `/tmp`、`/var/tmp`、`/dev/shm` 等 world-writable 位置；`ASK_GEMINI_BIN_UNRESTRICTED=1` 显式覆盖。
- **--target-dir 黑名单**：拒绝 `/`、`/etc`、`/usr`、`$HOME` 等过宽路径，避免污染 `~/.gemini/trustedFolders.json`。
- **--persist-to symlink 防护**：`is_symlink()` 拒绝 + `O_NOFOLLOW` 双重防御。

## 非显而易见的坑（都是血泪教训）

- **`str.format` 不会递归处理被替换进去的值**。prompt 模板里经常包含字面的 `{...}`（JSON / TS 示例），简单转义会污染用户内容。我们在 `bin/ask-gemini` 里用 sentinel 三遍替换的 `_render(template, **values)`，不走 `.format()`。`tests/test_brace_escape.py` 锁死了这套行为 —— 模板新增 `{name}` 占位符时，必须同步更新 `ALLOWED_PLACEHOLDERS` 白名单。
- **`trustedFolders.json` 的值必须是字符串**，不能是 dict。`preflight.py` 写入 `"TRUST_FOLDER"`（字符串），不要写 `{"trusted": true}`。Gemini 对 dict 形式是**静默拒绝**（不报错但不生效）。
- **Gemini 的 stream-json 每轮会发两条 `type=message`**：`role=user`（回显 prompt）+ `role=assistant`（真实回答）。`invoke._parse_events` 按 `role in {assistant, model}` 过滤 `content` / `delta`，否则 `response` 字段会混入 prompt 原文。
- **`gemini-3-pro-preview` 会发 `type=thought` 事件**（CoT），必须在 `_parse_events` 里 drop 掉，否则会污染 `response` 字段。`THOUGHT_EVENT_TYPES = {"thought", "thinking", "reasoning", "reflection", "scratchpad"}` —— Gemini 升级时新增类型要补进来。
- **默认剥离 `GOOGLE_CLOUD_PROJECT`**（在 `_prepare_env` 里）—— 组织订阅探测可能挂起。需要保留的话设 `ASK_GEMINI_KEEP_GCP=1`。
- **`GEMINI_BIN` 默认 `/opt/homebrew/bin/gemini`**（macOS Apple Silicon + Homebrew）。Linux / Intel Mac 要靠环境变量覆盖。**其他位置严禁硬编码绝对路径**，所有路径都通过 `Path(__file__).resolve().parent` 派生。

## second-opinion 模式 —— 盲审不变量

`--task` 参数必须描述**要解决的问题**，**绝不能**包含 Claude 的推理过程或建议的解决方案。这个 mode 的全部价值就是拿到一个独立异源的评审意见，泄露 Claude 的思维链等于自废武功。Wrapper 无法也不会自动检测这一点 —— 调用方必须自觉遵守。

## 新增一个 skill / mode 的步骤

1. 在 `prompts/<mode>.md` 添加 prompt 模板（字面花括号要写成 `{{` / `}}`）。
2. 在 `bin/ask-gemini` 的 `_parse_args` 的 `choices=[...]` 里加上新 mode，并补 `_compose_<mode>` 与 `_validate` 分支。
3. 把新增的 `{placeholder}` 加入 `tests/test_brace_escape.py::ALLOWED_PLACEHOLDERS` 白名单。
4. 如果 preflight 需要新的路径检查，扩展 `preflight.run_preflight`（它用显式关键字参数，不是 `**kwargs`）。
5. 通过 `smoke_test.sh` 抓一份活调用 envelope 存入 `examples/<mode>.json`。
6. **新增 `skills/<mode>/SKILL.md`**：参考现有 4 个 skill 的格式（frontmatter `name` + `description`，body 包含 When to use / Invocation / Output / When NOT to use）。description 要紧致而具体，因为 Claude 的路由完全依赖它。

## 沟通 & 文档语言约定

- 与用户沟通、写产物文档（包括本文件、测试报告、README 等）一律**使用中文**。
- 代码注释、日志消息、envelope 字段、SKILL.md（面向 Claude 路由用，需匹配训练语料）保持**英文**。

## 非平凡改动前必读

- `skills/<mode>/SKILL.md` —— 每个 skill 的调用契约（Claude 路由的依据）。
- `docs/usage.md` —— 用户视角的完整使用手册。
- `docs/implementation-plan.md` —— 冻结的设计决策和理由。
- `docs/test-report.md` —— 活调用冒烟结果、已知 bug 复盘（含 brace-escape、用户回显两起事故）。
- `docs/gemini-cli-reference.md` —— 精简后的上游 Gemini CLI 文档，flag 语义和 stream-json schema 的来源。
