# gemini-bridge

> **Claude Code → Google Gemini CLI 的只读桥** —— 给 Claude 补齐它做不到的 4 项能力，以 4 个独立 skill 暴露。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Tests](https://img.shields.io/badge/tests-243%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Dependencies](https://img.shields.io/badge/python%20deps-0-brightgreen)
![Verified](https://img.shields.io/badge/verified-Linux%20%7C%20macOS-success)

---

## 它能做什么

Claude 自身做不到 / 做不好的 4 件事，都委托给 Gemini：

| Skill ID | 用途 | Gemini 提供的核心能力 | Claude 单独做不了的原因 |
|---|---|---|---|
| `gemini-bridge:analyze` | 大代码库分析 | 1M+ token 上下文一次吃下整个 monorepo | Claude 上下文窗口不够 |
| `gemini-bridge:research` | 实时上网研究 | Google Search 接地 + URL 引用 | Claude 没接 Google Search |
| `gemini-bridge:second-opinion` | 异源模型盲审 | 不同模型谱系，独立视角 | Claude 自审有同源偏见 |
| `gemini-bridge:multimodal` | 图像 / PDF 解析 | 视觉 + 文档理解 | Claude 处理文件类型受限 |

整个 plugin 在 Gemini 端硬约束**只读**：`--approval-mode plan` + `policies/readonly.toml` 白名单 + 多层 argv 校验，不能写文件、不能执行命令。

---

## Quick start（3 行命令）

```
/plugin marketplace add cuishengjia/gemini-bridge
/plugin install gemini-bridge
```

然后**自然语言对话**——Claude 自动选用 skill：

> 帮我用 Gemini 查一下 Python 3.13 的最新发布日期。

期望：Claude 路由到 `gemini-bridge:research`，返回带真实域名 URL 引用的答案。**装上前先看一眼 [Prerequisites](#prerequisites必读缺一不可)**。

---

## Prerequisites（必读，缺一不可）

| 依赖 | 检查命令 | 安装 |
|---|---|---|
| **Claude Code** | `claude --version` | https://claude.ai/code |
| **Gemini CLI** | `gemini --version` | `npm i -g @google/gemini-cli` 或 https://geminicli.com |
| **Python ≥ 3.11** | `python3 --version` | 系统自带 / pyenv / brew |
| **Gemini 认证** | `gemini auth status` | `gemini auth login`（推荐，免费配额更高）<br>或 `export GEMINI_API_KEY=...`（[https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)） |

> **以上任意一项缺失，plugin 装上也用不了。** Claude Code 是 Plugin 宿主，Gemini CLI 是被桥接的对象——两边都要装好且认证通过。

### `gemini` 路径自动探测（v1.1.6+）

plugin 用 `shutil.which("gemini")` 自动从 `$PATH` 找 `gemini`：

| 你的环境 | 是否需要设 `GEMINI_BIN` |
|---|---|
| `npm i -g @google/gemini-cli`（任意 OS） | ❌ 不需要 |
| Homebrew (`brew install gemini-cli`) | ❌ 不需要 |
| nvm / 系统 PATH 上能 `which gemini` | ❌ 不需要 |
| `gemini` 装在 PATH 之外的位置 | ✅ `export GEMINI_BIN=<absolute path>` |

---

## 调用方式

### 方式 A：自然语言（**推荐**）

Claude 看对话语义自主选 skill，零命令记忆负担：

```
帮我用 Gemini 上网查 Tesla 2026 Q1 销量
→ Claude 路由 gemini-bridge:research

让 Gemini 分析一下 ~/myproject 的整体架构
→ Claude 路由 gemini-bridge:analyze

让 Gemini 盲审一下我这份 PR 设计
→ Claude 路由 gemini-bridge:second-opinion

帮我用 Gemini 看看这张截图里有什么按钮
→ Claude 路由 gemini-bridge:multimodal
```

### 方式 B：显式 slash form

```
/gemini-bridge:research <你的研究问题>
/gemini-bridge:analyze <分析需求>
/gemini-bridge:second-opinion <问题陈述>
/gemini-bridge:multimodal <prompt>
```

### 方式 C：直接 CLI 调用（绕过 Claude）

```bash
# 需要先 cd 到 plugin 目录，或用 find 定位
ASKGEMINI=$(find ~/.claude/plugins -path '*gemini-bridge*/bin/ask-gemini' -type f -executable | head -1)

# 1. 大代码库分析
"$ASKGEMINI" --mode analyze --target-dir ~/myproject --prompt "概述项目架构"

# 2. 实时研究
"$ASKGEMINI" --mode research --query "Python 3.13 最新发布日期"

# 3. 盲审
"$ASKGEMINI" --mode second-opinion \
  --task "PR 是否引入死锁风险?" --artefact-file ./pr.diff

# 4. 多模态
"$ASKGEMINI" --mode multimodal --image ./screenshot.png --prompt "界面有哪些按钮?"
```

完整 mode 参数、env vars、persist 机制、envelope schema → [docs/usage.md](docs/usage.md)

---

## How it works

```
User 对话
   ↓
Claude Code (skill 路由 / slash 解析)
   ↓
gemini-bridge:<mode>  (SKILL.md → bin/ask-gemini --mode <X>)
   ↓
preflight  (auth + GEMINI_BIN 探测 + 路径白名单)
   ↓
fallback chain:  gemini-3-pro-preview (300s)
              →  gemini-2.5-pro       (180s)
              →  gemini-2.5-flash     (120s)
   ↓
invoke (subprocess)  --approval-mode plan
                     -o stream-json
                     --policy policies/readonly.toml
   ↓
Gemini CLI  →  Google AI / Vertex AI
   ↓
streaming-json 解析  (CoT 过滤 + tool_calls 抓取)
   ↓
citations  (resolve grounding redirect URLs → 真实域名)
   ↓
envelope v1  {ok, mode, model_used, response, stats, tool_calls, ...}
   ↓
audit log JSONL  (~/.cache/ask-gemini-cli/, 10 MB rotating)
   ↓
stdout 一行 JSON  →  Claude 解析  →  用户答案
```

零第三方 Python 依赖（全 stdlib），全部代码 < 2000 行。详细架构 → [CLAUDE.md](CLAUDE.md)。

---

## 安全姿态（多层防御）

| 防御层 | 实现 |
|---|---|
| 调用端只读 | 硬编码 `--approval-mode plan` + `_assert_safety` 二次校验 argv |
| 工具白名单 | `policies/readonly.toml`：`read_file` / `glob` / `grep` / `google_web_search` 等 allow；`write_file` / `run_shell_command` / `edit` 全 deny；MCP 全 deny |
| `GEMINI_BIN` 路径黑名单 | 拒绝 `/tmp`、`/var/tmp`、`/dev/shm` 等 world-writable 位置；`ASK_GEMINI_BIN_UNRESTRICTED=1` 显式覆盖 |
| `--target-dir` 黑名单 | 拒绝 `/`、`/etc`、`/usr`、`$HOME` 等过宽路径，避免污染 `~/.gemini/trustedFolders.json` |
| `--persist-to` symlink 防护 | `is_symlink()` 拒绝 + `O_NOFOLLOW` 双重防御 |
| 三级模型 fallback | `gemini-3-pro-preview` → `gemini-2.5-pro` → `gemini-2.5-flash`，**仅** quota / timeout 触发；auth / bad_input / config 类错误一律不回退 |
| 审计日志 | `~/.cache/ask-gemini-cli/invocations.jsonl`，`0o600` 权限；`ASK_GEMINI_NO_LOG_RESPONSE=1` 摘要化；`ASK_GEMINI_LOG_DISABLED=1` 全关 |
| 第三方依赖 | **零** Python 包（全 stdlib），供应链零风险 |
| second-opinion 盲审 | 调用方需自觉不在 `--task` 泄露 Claude 的推理链；wrapper 不自动检测 |

---

## What's new

| 版本 | 关键变化 |
|---|---|
| **v1.1.8** | 完整 README 重写：troubleshooting / how-it-works / 调用方式 ABC |
| **v1.1.7** | SKILL.md 用 `find` 定位 binary，**首次调用一次性成功**（不依赖 `$CLAUDE_PLUGIN_ROOT`） |
| **v1.1.6** | `gemini` 自动从 `$PATH` 探测；解析 Gemini grounding redirect URL → 真实域名（彭博 / 路透 / 雪球等） |
| **v1.1.5** | marketplace.json 用 canonical `url` source 形式，5 次 install 兼容性 hotfix 收尾 |
| **v1.1.0** | 单一 skill 拆分成 4 个 mode-specific skill（`analyze` / `research` / `second-opinion` / `multimodal`） |
| **v1.0.0** | Initial public release |

完整 release notes → https://github.com/cuishengjia/gemini-bridge/releases

---

## Troubleshooting

### "Unknown command" / "Unknown skill" 报错

**症状**：装上后 `/gemini-bridge:research <...>` 报 "Unknown command"，自然语言路由也不触发。

**根因**：Claude Code 的 `installed_plugins.json` 注册表里有 stale entry（指向已删除的 install path），让 `/plugin install` 短路成 "already installed"。

**修复**：跑这段 python 自动清理（自带 `.bak` 备份）：

```bash
python3 << 'PY'
import json, shutil
from pathlib import Path

base = Path.home() / ".claude/plugins"

# installed_plugins.json
ip = base / "installed_plugins.json"
shutil.copy2(ip, ip.with_suffix(".json.bak"))
d = json.loads(ip.read_text())
removed = [k for k in list(d.get("plugins", {})) if "gemini-bridge" in k]
for k in removed:
    del d["plugins"][k]
ip.write_text(json.dumps(d, indent=2) + "\n")
print(f"installed_plugins.json: removed {removed}")

# known_marketplaces.json
km = base / "known_marketplaces.json"
shutil.copy2(km, km.with_suffix(".json.bak"))
d = json.loads(km.read_text())
removed = [k for k in list(d) if "gemini-bridge" in k]
for k in removed:
    del d[k]
km.write_text(json.dumps(d, indent=2) + "\n")
print(f"known_marketplaces.json: removed {removed}")
PY

# 同时清磁盘上的 stale 文件
rm -rf ~/.claude/plugins/marketplaces/gemini-bridge ~/.claude/plugins/cache/gemini-bridge*
```

然后**退出并重启** Claude Code，再 `/plugin marketplace add cuishengjia/gemini-bridge` + `/plugin install gemini-bridge`。

### "No such file or directory: /bin/ask-gemini"

**症状**：首次 bash 调用报 `/bin/ask-gemini` 找不到。

**根因**：Claude Code 2.1.x 在 bash tool 子进程里**不**导出 `$CLAUDE_PLUGIN_ROOT`，路径塌成空。

**修复**：升级到 v1.1.7+。SKILL.md 已改用 `find ~/.claude/plugins -path '*gemini-bridge*/bin/ask-gemini'` 单步定位，绕开 env var 依赖。

### "Host key verification failed" (SSH error)

**症状**：`/plugin install` 时报 `No ED25519 host key is known for github.com`。

**根因**：Claude Code 2.1.x 在某些路径下强行用 SSH 协议 clone，但用户 `~/.ssh/known_hosts` 没 GitHub 的 host key。

**修复**（一次性）：

```bash
ssh-keyscan -t rsa,ecdsa,ed25519 github.com >> ~/.ssh/known_hosts
```

### "Gemini binary not found" (config error)

**症状**：envelope `error.kind = "config"`，message 含 `/opt/homebrew/bin/gemini` 之类的路径。

**根因**：v1.1.5 及更早硬编码 macOS Apple Silicon 路径；v1.1.6+ 已改用 `shutil.which()` 自动探测。

**修复**：升级到 v1.1.6+，或显式 `export GEMINI_BIN=$(which gemini)`。

### `[Fact-Forcing Gate]` 之类的 hook 拦截首次 bash

**症状**：首次 bash 调用被 PreToolUse hook 拦截，要求 Claude 先陈述 facts。

**根因**：你**自己机器上**装的 hook（不是 plugin 提供的），常见于注重安全审计的工作流。

**修复**：这不是 plugin 问题。Claude 写完 facts 后第二次 bash 就放过——属正常工作流，不需要修。

---

## 兼容性

| 平台 | Claude Code 版本 | 状态 |
|---|---|---|
| Linux x86_64 (Ubuntu) | 2.1.119 | ✅ 已验证（research / 4 模式正常） |
| macOS (Apple Silicon) | 2.1.120 | ✅ 已验证 |
| macOS (Intel) | — | 未测，预期 work（同 Linux 路径） |
| Windows (WSL) | — | 未测，预期 work |
| Windows (native) | — | **未测**，可能要手动设 `ASK_GEMINI_CACHE_DIR` |

---

## 仓库结构

```
gemini-bridge/
├── .claude-plugin/{plugin,marketplace}.json   # plugin metadata
├── skills/                                    # 4 个 thin SKILL.md
│   ├── analyze/SKILL.md
│   ├── research/SKILL.md
│   ├── second-opinion/SKILL.md
│   └── multimodal/SKILL.md
├── bin/ask-gemini                             # 共享后端入口
├── lib/                                       # invoke / fallback / preflight / envelope / persist / audit_log / exit_codes / citations
├── prompts/                                   # 每个 mode 一个模板
├── policies/readonly.toml                     # allow/deny 规则
├── tests/                                     # 243 测试 + smoke
├── examples/                                  # 4 个 mode 各一份活调用 envelope
├── evals/                                     # research 模式 200 条评测
├── docs/                                      # 用户手册 + 设计文档 + envelope schema
├── CLAUDE.md / LICENSE / README.md
└── .gitignore
```

4 个 skill 共享 `bin/ask-gemini --mode <X>` 同一后端——零代码重复。

---

## 状态

| 维度 | 数值 |
|---|---|
| 单元测试 | **243 用例全绿**，~0.2s |
| 覆盖率 | `lib/` 整体 **94%** |
| 活调用冒烟 | 4 个 mode 各一份真实 envelope，见 [examples/](examples/) |
| Research 评测 | 200 条 query，详见 [docs/test-report.md](docs/test-report.md) |
| Envelope Schema | v1 已冻结（`ok`/`mode`/`response`/`stats`/`tool_calls`/...） |
| 第三方依赖 | **0** Python 包 |

---

## 进一步阅读

- 📘 **[docs/usage.md](docs/usage.md)** — 完整使用手册（4 个 mode 详解、env vars、persist、故障矩阵）
- 🧪 **[docs/test-report.md](docs/test-report.md)** — 历次冒烟、bug 复盘、200 条评测结果
- 🛠 **[CLAUDE.md](CLAUDE.md)** — 给开发者的架构主线 + 非显而易见的坑
- 📐 **[docs/implementation-plan.md](docs/implementation-plan.md)** — 设计决策与冻结的 schema
- 📋 **[docs/v2-requirements.md](docs/v2-requirements.md)** — v2 需求收集草稿
- 📑 **[docs/envelope-schema.json](docs/envelope-schema.json)** — Schema v1 JSON Schema
- 🐛 **[Issues](https://github.com/cuishengjia/gemini-bridge/issues)** — bug 报告 + 功能请求

---

## 贡献

```bash
git clone https://github.com/cuishengjia/gemini-bridge
cd gemini-bridge
python3 -m pytest tests/ -q
# 期望：243 passed in ~0.2s
```

跑活调用冒烟（消耗 Gemini 配额）：

```bash
ASK_GEMINI_LIVE=1 bash tests/smoke_test.sh
```

PR 欢迎。请遵循：
- Schema v1 envelope 冻结——任何字段改动都是 breaking
- 新增 mode 时按 [CLAUDE.md "新增一个 skill / mode 的步骤"](CLAUDE.md#新增一个-skill--mode-的步骤) 走完整流程
- 测试不动绿（`tests/` + 4 mode smoke）

---

## License

[MIT](LICENSE) © 2026 cuishengjia
