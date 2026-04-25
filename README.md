# gemini-bridge

> Claude Code → Google Gemini CLI 的**只读**桥，给 Claude 补齐它做不到的 4 项能力。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Tests](https://img.shields.io/badge/tests-220%20passing-brightgreen) ![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen) ![Python](https://img.shields.io/badge/python-3.11+-blue) ![Dependencies](https://img.shields.io/badge/python%20deps-0-brightgreen)

---

## 为什么需要它

Claude 自身做不到 / 做不好的 4 件事，全都委托给 Gemini：

| Mode | Gemini 提供的能力 | Claude 单独做不了的原因 |
|---|---|---|
| `analyze` | 1M+ token 一次吃下整个代码库 | Claude 上下文窗口不够 |
| `research` | Google 实时检索 + URL 引用 | Claude 没接 Google Search |
| `second-opinion` | 异源模型独立盲审 | Claude 自审有同源偏见 |
| `multimodal` | 图像 / PDF / 视频帧解析 | Claude 处理文件类型受限 |

整个 skill 在 Gemini 端用 `--approval-mode plan` + 策略白名单启动——硬约束**只读**，不能写文件、不能执行命令。详细机制见 [`skills/ask-gemini-cli/README.md` §8](skills/ask-gemini-cli/README.md)。

---

## Prerequisites（必读，缺一不可）

| 依赖 | 检查命令 | 安装 |
|---|---|---|
| **Claude Code** | `claude --version` | https://claude.ai/code |
| **Gemini CLI** | `gemini --version` | `npm i -g @google/gemini-cli` 或 https://geminicli.com |
| **Python ≥ 3.11** | `python3 --version` | 系统自带 / pyenv |
| **Gemini 认证** | `gemini auth status` | `gemini auth login`（推荐，免费配额更高）<br>或 `export GEMINI_API_KEY=...`（[https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)） |

> **没有以上任何一项，plugin 装上也用不了。** Claude Code 是 Plugin 宿主；Gemini CLI 是被桥接的对象——两边都要装好且认证通过。

---

## 安装

```bash
# 1. 添加市场
/plugin marketplace add cuishengjia/gemini-bridge

# 2. 安装 plugin
/plugin install gemini-bridge
```

安装后 Claude Code 自动发现 `ask-gemini-cli` skill，遇到合适场景会自主调用——你无需手动敲命令。

### 验证安装

让 Claude 跑一句研究问题（任意 prompt 含 "上网搜" / "research" 等关键词均可）：

> 帮我用 Gemini 查一下 Python 3.13 的最新发布日期。

Claude 应自主选择 `gemini-bridge:ask-gemini-cli` skill，模式 `research`，返回带 URL 引用的答案。

---

## 4 个 Mode 各举一例

```bash
# 1. 分析整个代码库
ask-gemini --mode analyze --target-dir ~/myproject --prompt "概述项目架构"

# 2. 实时研究
ask-gemini --mode research --query "Python 3.13 最新发布日期"

# 3. 让 Gemini 盲审一份方案 / PR
ask-gemini --mode second-opinion --task "PR 是否引入死锁风险?" --artefact-file ./pr.diff

# 4. 解析一张图
ask-gemini --mode multimodal --image ./screenshot.png --prompt "界面有哪些按钮?"
```

完整的 mode 参数、env vars、persist 机制、故障排查 → [`skills/ask-gemini-cli/README.md`](skills/ask-gemini-cli/README.md)

---

## 安全姿态

| 防御层 | 实现 |
|---|---|
| 调用端只读 | 硬编码 `--approval-mode plan` + `_assert_safety` 二次校验 |
| 工具白名单 | `policies/readonly.toml`：`read_file` / `glob` / `grep` / `google_web_search` 等 allow；`write_file` / `run_shell_command` / `edit` 全 deny；MCP 全 deny |
| `GEMINI_BIN` 路径黑名单 | 拒绝 `/tmp`、`/var/tmp`、`/dev/shm` 等 world-writable 位置 |
| `--target-dir` 黑名单 | 拒绝 `/`、`/etc`、`/usr`、`$HOME` 等过宽路径，避免污染 `~/.gemini/trustedFolders.json` |
| `--persist-to` symlink 防护 | `is_symlink()` 拒绝 + `O_NOFOLLOW` 防御 |
| 三级模型 fallback | `gemini-3-pro-preview` → `gemini-2.5-pro` → `gemini-2.5-flash`，仅 quota / timeout 触发 |
| 审计日志 | `~/.cache/ask-gemini-cli/invocations.jsonl`，`0o600` 权限；`ASK_GEMINI_NO_LOG_RESPONSE=1` 摘要化；`ASK_GEMINI_LOG_DISABLED=1` 全关 |
| 第三方依赖 | **零** Python 包（全部 stdlib），供应链零风险 |

---

## 状态

| 维度 | 数值 |
|---|---|
| 单元测试 | **220 用例全绿**，~0.2s |
| 覆盖率 | `lib/` 整体 **94%** |
| 活调用冒烟 | 4 个 mode 各一份真实 envelope，见 [`skills/ask-gemini-cli/examples/`](skills/ask-gemini-cli/examples/) |
| Research 模式评测 | 200 条 query，详见 [`skills/ask-gemini-cli/docs/test-report.md`](skills/ask-gemini-cli/docs/test-report.md) |
| Envelope Schema | v1 已冻结（`ok`/`mode`/`response`/`stats`/`tool_calls`/...） |
| 平台 | macOS / Linux 已验；Windows 未测 |

---

## 进一步阅读

- 📘 **[skills/ask-gemini-cli/README.md](skills/ask-gemini-cli/README.md)** — 完整使用手册（4 个 mode 详解、env vars、persist、故障矩阵）
- 📋 **[skills/ask-gemini-cli/SKILL.md](skills/ask-gemini-cli/SKILL.md)** — Claude 的调用契约（skill 规格本身）
- 🧪 **[skills/ask-gemini-cli/docs/test-report.md](skills/ask-gemini-cli/docs/test-report.md)** — 历次冒烟、bug 复盘、200 条评测结果
- 🛠 **[CLAUDE.md](CLAUDE.md)** — 给开发者的架构主线 + 非显而易见的坑
- 📐 **[docs/](docs/)** — 设计决策、Gemini CLI 精简参考、v2 需求草稿

---

## 贡献

欢迎 issue / PR。开发流程：

```bash
git clone https://github.com/cuishengjia/gemini-bridge
cd gemini-bridge/skills/ask-gemini-cli
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
