# gemini-bridge

> Claude Code → Google Gemini CLI 的**只读**桥，给 Claude 补齐它做不到的 4 项能力——以 4 个独立 skill 暴露。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Tests](https://img.shields.io/badge/tests-220%20passing-brightgreen) ![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen) ![Python](https://img.shields.io/badge/python-3.11+-blue) ![Dependencies](https://img.shields.io/badge/python%20deps-0-brightgreen)

---

## 4 个 skill 对应 4 种 Claude 做不到的能力

| Skill ID | 用途 | Gemini 提供的核心能力 |
|---|---|---|
| `gemini-bridge:analyze` | 大代码库分析 | 1M+ token 上下文一次吃下整个 monorepo |
| `gemini-bridge:research` | 实时上网研究 | Google Search 接地 + URL 引用 |
| `gemini-bridge:second-opinion` | 异源模型盲审 | 不同模型谱系，独立视角 |
| `gemini-bridge:multimodal` | 图像 / PDF 解析 | 视觉 + 文档理解 |

整个 plugin 在 Gemini 端硬约束**只读**：`--approval-mode plan` + `policies/readonly.toml` 白名单 + 多层 argv 校验，不能写文件、不能执行命令。详细机制见 [docs/usage.md §8](docs/usage.md)。

---

## Prerequisites（必读，缺一不可）

| 依赖 | 检查命令 | 安装 |
|---|---|---|
| **Claude Code** | `claude --version` | https://claude.ai/code |
| **Gemini CLI** | `gemini --version` | `npm i -g @google/gemini-cli` 或 https://geminicli.com |
| **Python ≥ 3.11** | `python3 --version` | 系统自带 / pyenv |
| **Gemini 认证** | `gemini auth status` | `gemini auth login`（推荐，免费配额更高）<br>或 `export GEMINI_API_KEY=...`（[https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)） |

> **没有以上任何一项，plugin 装上也用不了。** Claude Code 是 Plugin 宿主；Gemini CLI 是被桥接的对象——两边都要装好且认证通过。

**关于 `gemini` 路径自动探测（v1.1.6+）**：plugin 用 `shutil.which("gemini")` 自动从 `$PATH` 找 `gemini`，所以 Linux / Intel Mac / npm 全局安装的用户**无需**手动设 `GEMINI_BIN`。只有当 `gemini` 不在 `$PATH` 上时才需要 `export GEMINI_BIN=<path>`。

---

## 安装

```
/plugin marketplace add cuishengjia/gemini-bridge
/plugin install gemini-bridge
```

安装后 4 个 skill 都自动出现，Claude Code 看对话场景自主选哪一个调用——你无需手动敲命令。

### 验证安装

随便给 Claude 一句典型场景：

> 帮我用 Gemini 查一下 Python 3.13 的最新发布日期。

Claude 应自主选 `gemini-bridge:research`，返回带 URL 引用的答案。换 prompt 让 Claude 去分析一个本地大项目，应该选 `gemini-bridge:analyze`。

---

## 4 个 skill 各举一例（直接 CLI 调用，绕过 Claude 自动路由）

```bash
# gemini-bridge:analyze
bin/ask-gemini --mode analyze --target-dir ~/myproject --prompt "概述项目架构"

# gemini-bridge:research
bin/ask-gemini --mode research --query "Python 3.13 最新发布日期"

# gemini-bridge:second-opinion
bin/ask-gemini --mode second-opinion --task "PR 是否引入死锁风险?" --artefact-file ./pr.diff

# gemini-bridge:multimodal
bin/ask-gemini --mode multimodal --image ./screenshot.png --prompt "界面有哪些按钮?"
```

完整 mode 参数、env vars、persist 机制、故障排查 → [docs/usage.md](docs/usage.md)

---

## 安全姿态

| 防御层 | 实现 |
|---|---|
| 调用端只读 | 硬编码 `--approval-mode plan` + `_assert_safety` 二次校验 |
| 工具白名单 | `policies/readonly.toml`：`read_file` / `glob` / `grep` / `google_web_search` 等 allow；`write_file` / `run_shell_command` / `edit` 全 deny；MCP 全 deny |
| `GEMINI_BIN` 路径黑名单 | 拒绝 `/tmp`、`/var/tmp`、`/dev/shm` 等 world-writable 位置 |
| `--target-dir` 黑名单 | 拒绝 `/`、`/etc`、`/usr`、`$HOME` 等过宽路径，避免污染 `~/.gemini/trustedFolders.json` |
| `--persist-to` symlink 防护 | `is_symlink()` 拒绝 + `O_NOFOLLOW` |
| 三级模型 fallback | `gemini-3-pro-preview` → `gemini-2.5-pro` → `gemini-2.5-flash`，仅 quota / timeout 触发 |
| 审计日志 | `~/.cache/ask-gemini-cli/invocations.jsonl`，`0o600` 权限；`ASK_GEMINI_NO_LOG_RESPONSE=1` 摘要化；`ASK_GEMINI_LOG_DISABLED=1` 全关 |
| 第三方依赖 | **零** Python 包（全部 stdlib），供应链零风险 |

---

## 仓库结构（v1.1.0 后）

```
gemini-bridge/
├── .claude-plugin/{plugin,marketplace}.json   # plugin metadata
├── skills/                                    # 4 个 thin SKILL.md
│   ├── analyze/SKILL.md
│   ├── research/SKILL.md
│   ├── second-opinion/SKILL.md
│   └── multimodal/SKILL.md
├── bin/ask-gemini                             # 共享后端入口
├── lib/                                       # invoke / fallback / preflight / envelope / persist / audit_log / exit_codes
├── prompts/                                   # 每个 mode 一个模板
├── policies/readonly.toml                     # allow/deny 规则
├── tests/                                     # 220 测试 + smoke
├── examples/                                  # 4 个 mode 各一份活调用 envelope
├── evals/                                     # research 模式 200 条评测
├── docs/                                      # 用户手册 + 设计文档 + envelope schema
├── CLAUDE.md / LICENSE / README.md
└── .gitignore
```

4 个 skill 共享 `bin/ask-gemini --mode <X>` 同一后端——无代码重复。

---

## 状态

| 维度 | 数值 |
|---|---|
| 单元测试 | **220 用例全绿**，~0.2s |
| 覆盖率 | `lib/` 整体 **94%** |
| 活调用冒烟 | 4 个 mode 各一份真实 envelope，见 [examples/](examples/) |
| Research 评测 | 200 条 query，详见 [docs/test-report.md](docs/test-report.md) |
| Envelope Schema | v1 已冻结（`ok`/`mode`/`response`/`stats`/`tool_calls`/...） |
| 平台 | macOS / Linux 已验；Windows 未测 |

---

## 进一步阅读

- 📘 **[docs/usage.md](docs/usage.md)** — 完整使用手册（4 个 mode 详解、env vars、persist、故障矩阵）
- 🧪 **[docs/test-report.md](docs/test-report.md)** — 历次冒烟、bug 复盘、200 条评测结果
- 🛠 **[CLAUDE.md](CLAUDE.md)** — 给开发者的架构主线 + 非显而易见的坑
- 📐 **[docs/implementation-plan.md](docs/implementation-plan.md)** — 设计决策与冻结的 schema
- 📋 **[docs/v2-requirements.md](docs/v2-requirements.md)** — v2 需求收集草稿
- 📑 **[docs/envelope-schema.json](docs/envelope-schema.json)** — Schema v1 JSON Schema

---

## 贡献

```bash
git clone https://github.com/cuishengjia/gemini-bridge
cd gemini-bridge
python3 -m pytest tests/ -q
# 期望：220 passed in ~0.2s
```

跑活调用冒烟（消耗 Gemini 配额）：

```bash
ASK_GEMINI_LIVE=1 bash tests/smoke_test.sh
```

---

## License

[MIT](LICENSE) © 2026 cuishengjia
