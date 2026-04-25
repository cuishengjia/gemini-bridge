# GeminiCLI4CC

A Claude Code 开发工作区，承载 **`ask-gemini-cli`** 这个 skill 的源码、测试、评测数据与设计文档。

`ask-gemini-cli` 是一个把 Claude Code 桥接到 Google `gemini` CLI 的**只读** skill。它让 Claude 在四种自身难以胜任的场景下，把任务卸载给 Gemini：

1. **analyze** — 1M+ token 级别的大上下文代码库分析
2. **research** — 基于 Google Search 实时检索、带 URL 引用的研究
3. **second-opinion** — 让异源模型做**盲审**独立评审
4. **multimodal** — 图像 / PDF / 视频帧分析

Gemini 以 `approval-mode=plan` + 策略白名单启动，硬约束是只读：不能写文件、不能执行命令。

## 仓库布局

```
GeminiCLI4CC/
├── CLAUDE.md                          # 给 Claude Code 的工作区指令（架构主线、坑、约定）
├── docs/
│   ├── implementation-plan.md         # 冻结的设计决策
│   └── gemini-cli-reference.md        # 精简后的上游 Gemini CLI 参考
└── .claude/skills/ask-gemini-cli/     # skill 本体（下面的部分会被发版到 ~/.claude/skills/）
    ├── SKILL.md                       # skill 规格（面向 Claude 的调用契约）
    ├── MIGRATION.md                   # 项目本地 → 用户全局的迁移清单
    ├── bin/ask-gemini                 # 唯一入口（Python 脚本，无 .py 后缀）
    ├── lib/                           # invoke / fallback / preflight / envelope / persist / audit_log / exit_codes
    ├── prompts/                       # 每个 mode 一个 .md 模板
    ├── policies/readonly.toml         # allow/deny 规则，通过 gemini --policy 传入
    ├── tests/                         # pytest 套件（203 用例，94% 覆盖）+ smoke_test.sh
    ├── docs/                          # envelope-schema.json + test-report.md
    ├── examples/                      # 四个 mode 各一份活调用 envelope
    └── evals/                         # research 模式 200 条评测 harness + 结果
```

`docs/`、`CLAUDE.md`、本 README 只是支撑材料，**不随 skill 发布**。发版到 `~/.claude/skills/ask-gemini-cli/` 时只复制 `.claude/skills/ask-gemini-cli/` 目录本身。

## 快速上手

### 前置

- macOS / Linux（Windows 需手动设 `ASK_GEMINI_CACHE_DIR`）
- Python 3.11+
- Gemini CLI：`brew install gemini` 或从 https://geminicli.com 安装；默认路径 `/opt/homebrew/bin/gemini`，其它路径用 `GEMINI_BIN` 环境变量指定
- 已完成 Gemini 登录（`gemini auth login` 或 OAuth 走 `~/.gemini/`）

### 跑测试

```bash
cd .claude/skills/ask-gemini-cli
python3 -m pytest -q                            # 全量 mock，~0.2s
python3 -m pytest --cov=lib --cov-report=term   # 带覆盖率
```

### 发一次真实调用（消耗 Gemini 配额）

```bash
cd .claude/skills/ask-gemini-cli
./bin/ask-gemini --mode research --query "What's the latest Python stable release?"
```

输出是一行 JSON envelope（Schema v1，见 `docs/envelope-schema.json`）。

### 在 Claude Code 里用

把 `.claude/skills/ask-gemini-cli/` 复制到 `~/.claude/skills/ask-gemini-cli/` 后重启 Claude Code，它会作为 skill 被自动发现。调用契约写在 `SKILL.md` 里，Claude 会自己读。

## 核心不变量

- **只读强制**：`invoke.build_argv` 硬编码 `--approval-mode plan`、`-o stream-json`、`--policy policies/readonly.toml`。`_assert_safety` 在启动子进程前再次核对 argv，拒绝任何危险标志。
- **三级回退链**：`gemini-3-pro-preview`（300s）→ `gemini-2.5-pro`（180s）→ `gemini-2.5-flash`（120s）。**仅**在 quota / 瞬时错误时触发回退；auth / bad_input / config 类错误一律不回退。
- **Envelope Schema v1 已冻结**。字段：`ok`、`mode`、`model_used`、`fallback_triggered`、`attempts`、`response`、`stats`、`tool_calls`、`persisted_to`、`warnings`、`error`。改动都是破坏性变更。
- **二次过滤 CoT**：Gemini 有时会把 `type=thought` / `thinking` / `reasoning` 事件流式发出；`invoke._parse_events` 通过白名单过滤，只保留 `assistant` / `model` 角色的 `content`。

## 质量状况（v1 发版时）

| 维度 | 数值 |
|---|---|
| 单测 | 203 用例全绿，~0.2s |
| 覆盖率 | lib/ 整体 94% |
| 活调用冒烟 | 4 个 mode 各抓一份 envelope（`examples/`） |
| research 模式评测 | 200 条 query，见 `docs/test-report.md §10` |

评测中明确暴露的已知限制：runner 层没有令牌桶/速率限制原语，高并发（c=10）会被 `cloudcode-pa.googleapis.com` 的 per-model 配额挡掉。生产使用建议 `concurrency=2-3`。

## 进一步阅读

- **`.claude/skills/ask-gemini-cli/SKILL.md`** — skill 规格、调用契约
- **`CLAUDE.md`** — 架构主线 + 非显而易见的坑（brace escape、用户回显、`trustedFolders.json` dict 陷阱等）
- **`.claude/skills/ask-gemini-cli/docs/test-report.md`** — 冒烟结果、两起历史 bug 复盘、200 条评测 run 的 quota 风暴记录
- **`docs/implementation-plan.md`** — 冻结的设计决策与原因

## License

私有仓库，未公开。
