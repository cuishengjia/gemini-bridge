# gemini-bridge v1 工作日志

整理 v1.0.0 → v1.1.8 的完整开发过程：决策依据、踩过的坑、最终交付物、未完成事项。供将来回看 + v2 启动时参考。

> **统计**：1 仓库 / 4 skill / 9 个 release / 8 个 bug / 243 测试 / 94% 覆盖 / 0 第三方 Python 依赖 / 已部署到 Anthropic 官方提交 + awesome-claude-code 待提交。

---

## 1. 项目定位

gemini-bridge 是一个**只读** Claude Code plugin，把 Claude Code 桥接到 Google `gemini` CLI，给 Claude 补齐它做不到的 4 项能力：

| Skill | 用途 | Claude 自己做不了的原因 |
|---|---|---|
| `gemini-bridge:analyze` | 1M+ token 大代码库分析 | Claude 上下文窗口不够 |
| `gemini-bridge:research` | Google Search 接地的实时研究 | Claude 没接 Google Search |
| `gemini-bridge:second-opinion` | 异源模型盲审 | Claude 自审有同源偏见 |
| `gemini-bridge:multimodal` | 图像 / PDF / 视频帧 | Claude 处理文件类型受限 |

**核心约束**：调用 Gemini 时硬编码 `--approval-mode plan` + `policies/readonly.toml` 白名单，不能写文件、不能执行命令。**多层防御**——argv 二次校验、路径黑名单、symlink 防护。

---

## 2. 仓库信息

| 项 | 值 |
|---|---|
| 仓库 URL | https://github.com/cuishengjia/gemini-bridge |
| GitHub 账号 | cuishengjia（noreply email `141436024+cuishengjia@users.noreply.github.com`） |
| License | MIT |
| Latest release | v1.1.8 |
| Default branch | main |
| Visibility | Public |
| 安装命令 | `/plugin marketplace add cuishengjia/gemini-bridge` + `/plugin install gemini-bridge` |
| 本地开发路径 | `/Users/cuishengjia/MyAIProjects/GeminiCLI4CC` |

---

## 3. 版本时间线

| 版本 | 日期 | 关键变化 | 触发事件 |
|---|---|---|---|
| v1.0.0 | 2026-04-25 | Initial public release（单 commit squash 后） | 准备开源 |
| v1.1.0 | 2026-04-25 | **BREAKING**：单一 skill 拆成 4 个 mode-specific skill | 提升 Claude 路由准确性 |
| v1.1.1 | 2026-04-25 | `marketplace.json` source `"."` → `"./"` | Linux Claude Code 2.1.120 报 "source type not supported" |
| v1.1.2 | 2026-04-25 | source → `{"source": "github", "repo": "..."}` | v1.1.1 仍失败 |
| v1.1.3 | 2026-04-25 | source → `{"source": "url", "url": "https://..."}` | v1.1.2 触发 SSH host key 错 |
| v1.1.4 | 2026-04-26 | source → `{"source": "local", "path": "."}` | v1.1.3 仍走 SSH（Claude Code 2.1.x bug） |
| v1.1.5 | 2026-04-26 | source 回归 `{"source": "url", "url": "https"}`——canonical | bug reporter 报 "Invalid schema" on v1.1.4，研究后发现 `local` 不在官方 schema |
| v1.1.6 | 2026-04-26 | `lib/citations.py` + `shutil.which()` GEMINI_BIN auto-detect | Linux 用户 testrun 暴露两个 UX bug |
| v1.1.7 | 2026-04-26 | SKILL.md 改用 `find` 单步定位 binary | testrun 显示 `$CLAUDE_PLUGIN_ROOT` 在 bash tool 子进程没被展开 |
| v1.1.8 | 2026-04-26 | 完整 README 重写（160 → 357 行） | 主线闭合后需要更好的对外文档 |

完整 release notes：https://github.com/cuishengjia/gemini-bridge/releases

---

## 4. 已知 bug 及修复（9 个）

### 4.1 Open source PII 泄露（修于 v1.0.0 前）

**症状**：`/Users/cuishengjia/` 出现在 160+ git-tracked 文件里（`evals/results/`、`docs/test-report.md`、`docs/implementation-plan.md`），`.idea/` 也被 git 跟踪。

**根因**：开发期没准备好做 open source。`.gitignore` 不全。

**修复**：
- `git rm --cached` 移除 `evals/results/` (242 文件) 和 `.idea/` (5 文件)
- 替换 doc 里 4 处 `/Users/cuishengjia/...` → `<repo-root>/...`
- 补全 `.gitignore`：`.idea/` `.vscode/` `.claude/settings.local.json` `evals/results/`
- **整个 git 历史 squash 成单 commit** —— 抹掉所有早期 PII 痕迹

**验证**：`git ls-files | xargs grep -l "/Users/cuishengjia"` → 无结果。

### 4.2 Plugin marketplace source 格式不兼容（v1.1.1 → v1.1.5）

**症状**：用户装不上，从 "source type not supported" 一路换成 SSH host key 错、再换成 "Invalid schema"。

**根因**：marketplace.json 的 `plugins[].source` 字段在不同 Claude Code 版本接受的形式不一样。我盲改了 5 次：

| 版本 | source | 报错 |
|---|---|---|
| v1.0.0/v1.1.0 | `"."` | "source type not supported" (string 格式 dot 不接受) |
| v1.1.1 | `"./"` | 同上 |
| v1.1.2 | `{"source": "github", "repo": "..."}` | clone 走 SSH，host key fail |
| v1.1.3 | `{"source": "url", "url": "https"}` | 同上（Claude Code 2.1.x 仍把 github URL 转 SSH） |
| v1.1.4 | `{"source": "local", "path": "."}` | "Invalid schema" — `local` 不在官方 schema |
| **v1.1.5** | `{"source": "url", "url": "https"}` | ✅ 装成 |

**最终修复（v1.1.5）**：调研 Anthropic 官方 `claude-plugins-official` marketplace 160 个 plugin 的 source 形式分布——

| 形式 | 占比 |
|---|---|
| `{"source": "url", "url": "..."}` | 53%（最主流） |
| 字符串相对路径 `"./..."` | 30% |
| `{"source": "git-subdir", ...}` | 16% |
| `{"source": "github", "repo": "..."}` | 0.6% |
| `{"source": "local", ...}` | 0% |

→ 选 `url` 形式，最经验证、最广泛兼容。

**经验教训**：bug reporter 推荐改成 `type` 作为内层 discriminator，**经验证错的**——官方 schema 是 `source`。**不要盲信 bug 报告，用经验数据验证**。

### 4.3 SSH host key verification failed（Claude Code 2.1.x 客户端 bug）

**症状**：`/plugin install` 报 `No ED25519 host key is known for github.com and you have requested strict checking`。

**根因**：Claude Code 2.1.x 在 plugin 拉取阶段，**不论** marketplace.json 写的是 HTTPS URL，都强制走 SSH。`temp_github_*` 临时目录命名也对应 GitHub-specific clone handler。`~/.ssh/known_hosts` 没有 GitHub host key 就崩。

**修复**：用户侧一次性补 host key：

```bash
ssh-keyscan -t rsa,ecdsa,ed25519 github.com >> ~/.ssh/known_hosts
```

**plugin 端无法修**——已写进 README troubleshooting。

### 4.4 `$CLAUDE_PLUGIN_ROOT` 在 bash tool 子进程不展开

**症状**：Claude 跑 `"$CLAUDE_PLUGIN_ROOT/bin/ask-gemini" ...` 时，`$CLAUDE_PLUGIN_ROOT` 是空字符串，路径塌成 `/bin/ask-gemini`，exit 127。

**根因**：Claude Code 2.1.x 没把 `$CLAUDE_PLUGIN_ROOT` 导出到 bash tool 子进程。Claude（模型）能自我恢复（list cache 目录推断真实路径），但首次调用必败一次。

**修复（v1.1.7）**：4 个 SKILL.md 把 `$CLAUDE_PLUGIN_ROOT` 替换为单步 `find`：

```bash
"$(find ~/.claude/plugins -path '*gemini-bridge*/bin/ask-gemini' -type f -executable 2>/dev/null | head -1)" \
  --mode <X> --... ...
```

**验证**：post-v1.1.7 testrun 第一次 bash 直接成功。

### 4.5 GEMINI_BIN 默认值是 macOS Apple Silicon 专用

**症状**：Linux 用户报 envelope `error.kind: "config"`，message 含 `/opt/homebrew/bin/gemini`。

**根因**：`lib/invoke.py` 硬编码 `DEFAULT_GEMINI_BIN = "/opt/homebrew/bin/gemini"`。Linux/Intel-Mac/npm 全局装的 gemini 都不在这个路径。

**修复（v1.1.6）**：3 级 resolution：

```python
def gemini_bin() -> str:
    if explicit := os.environ.get("GEMINI_BIN"):
        return _validate_bin_path(explicit)
    if found := shutil.which("gemini"):
        return _validate_bin_path(found)
    return _validate_bin_path(DEFAULT_GEMINI_BIN)
```

`lib/preflight.py::_check_binary()` 也改成调 `invoke.gemini_bin()` 共用同一逻辑。

**经验教训**：跨平台默认值应该用 `shutil.which()` 而不是硬编码路径。

### 4.6 Gemini grounding redirect URL 不透明

**症状**：research mode 返回的 sources 是 `vertexaisearch.cloud.google.com/grounding-api-redirect/<token>`，用户看不到真实域名（Bloomberg / Reuters / 雪球等）。

**根因**：Gemini API 为了 attribution tracking，把所有 search 引用包成 redirect URL。

**修复（v1.1.6）**：新增 `lib/citations.py`，response 里的 redirect URL 通过并行 HEAD 请求（8 路 ThreadPoolExecutor，5s 超时/URL）解析到 Location header 的真实 URL，原地替换。失败时保留原 redirect URL（graceful degradation）。

`ASK_GEMINI_NO_RESOLVE_CITATIONS=1` 可关闭（offline / air-gapped 用）。当解析了 N 条 URL，envelope `warnings[]` 加 `resolved_N_grounding_urls`。

**测试**：`tests/test_citations.py` 17 个 case 含 mock urlopen、参数化、idempotent、超时、404、no Location header 等边缘场景。

### 4.7 `installed_plugins.json` stale entry 阻塞 plugin 升级

**症状**：装上 v1.1.7 后，`/gemini-bridge:research` 报 "Unknown command: /gemini-bridge:research"，自然语言路由也不触发。

**根因**：Claude Code 内部有 `~/.claude/plugins/installed_plugins.json` 注册表。`gemini-bridge` 的 entry 残留指向已被 `rm -rf` 的旧 install path（v1.1.5 的 SHA），但 version 字段是 1.1.7。`/plugin install gemini-bridge` 看到 entry 觉得"已装"，短路退出，不重新拉文件。

**修复（用户侧操作，已写进 README）**：

```bash
python3 << 'PY'
import json, shutil
from pathlib import Path
base = Path.home() / ".claude/plugins"
ip = base / "installed_plugins.json"
shutil.copy2(ip, ip.with_suffix(".json.bak"))
d = json.loads(ip.read_text())
removed = [k for k in list(d.get("plugins", {})) if "gemini-bridge" in k]
for k in removed:
    del d["plugins"][k]
ip.write_text(json.dumps(d, indent=2) + "\n")
print(f"removed {removed}")
# 同样处理 known_marketplaces.json
PY
rm -rf ~/.claude/plugins/marketplaces/gemini-bridge ~/.claude/plugins/cache/gemini-bridge*
# 重启 Claude Code → /plugin marketplace add → /plugin install
```

**经验教训**：Claude Code 2.1.x 的 `marketplace remove` 不一定真的清 stale state。**升级时要 uninstall + install，或直接物理清 + 修 json**。

### 4.8 Bug reporter 错误推荐 `type` 作为 schema discriminator

**症状**：bug reporter 提交 issue 说 schema 用 `"type"` 而非 `"source"` 作内层字段。

**根因**：reporter 真的遇到了报错（v1.1.4 的 `local` 不在 schema），但他对 schema 的判断错了。

**调研验证**：
- 官方文档 https://code.claude.com/docs/en/plugin-marketplaces 列出 5 种合法 source，全用 `source` 作 discriminator
- 本机 184 个真实 plugin entry：114 用 `source`，0 用 `type`

**修复（v1.1.5）**：换成 canonical `url` 形式，绕开真正问题（`local` 不在 schema），不采纳 reporter 关于 `type` 的错误建议。

**经验教训**：**不要盲信 bug 报告**——reporter 的诊断和 root cause 经常不一致。用经验数据交叉验证。

### 4.9 临时 `.tmp.md` 文件被误 commit

**症状**：v1.1.1 commit 时 `git add -A` 把 `message.md`（用户本地 scratch）和 `.release-notes-v1.1.1.tmp.md`（我用来传 release notes 的临时文件）一起 commit 推上去。

**修复**：amend + force push，把这些文件从 commit 里移掉，加 `.gitignore` 排除：`message.md` `testrun.md` `*-suggestion.md` `*.tmp.md` `.release-notes-*.md`。后续 commit 改用 **scoped staging**：`git add .claude-plugin/ skills/ tests/`，不再用 `git add -A`。

**经验教训**：scoped staging > `add -A`，永远更安全。

---

## 5. 关键架构决策

### 5.1 单 skill 4 mode → 4 独立 skill（v1.1.0）

**Before**：单 `ask-gemini-cli` skill，调用时传 `--mode <X>` 选模式。
**After**：4 个独立 skill (`gemini-bridge:analyze` / `:research` / `:second-opinion` / `:multimodal`)，共享同一后端 `bin/ask-gemini`。

**理由**：
- 4 个独立 SKILL.md description 让 Claude 路由更精准
- 用户 / 日志看到 `gemini-bridge:research` 立刻知道在干什么
- 共享后端零代码重复

**代价**：v1.0.0 → v1.1.0 是 BREAKING，但 v1.0.0 才发布 30 分钟，没用户。

### 5.2 自托管 marketplace（仓库 IS marketplace）

`marketplace.json` 在仓库根的 `.claude-plugin/`，且 `plugins[0].source` 指向同一仓库的 GitHub URL：

```json
{
  "name": "gemini-bridge",
  "owner": {"name": "cuishengjia"},
  "plugins": [{
    "name": "gemini-bridge",
    "source": {"source": "url", "url": "https://github.com/cuishengjia/gemini-bridge.git"}
  }]
}
```

用户一条命令就装（`/plugin marketplace add cuishengjia/gemini-bridge` + `install`），无需单独的 marketplace 仓库。

### 5.3 Schema v1 envelope 冻结

`docs/envelope-schema.json` 锁死所有字段（`ok` / `mode` / `model_used` / `fallback_triggered` / `attempts` / `response` / `stats` / `tool_calls` / `persisted_to` / `warnings` / `error`），任何改动算 breaking。**对外契约不变**让用户 / 自动化能稳定 parse。

### 5.4 三级模型 fallback

`gemini-3-pro-preview` (300s) → `gemini-2.5-pro` (180s) → `gemini-2.5-flash` (120s)。**仅** quota / timeout 触发；auth / bad_input / config 类错误一律不回退（避免掩盖真实错误）。

### 5.5 零第三方 Python 依赖

全部用 stdlib（`urllib` / `subprocess` / `json` / `pathlib` / `concurrent.futures`）。供应链零风险，安装无 `pip install`。代价：写 HTTP redirect 解析比用 `requests` 多一些行数。

### 5.6 多层只读防御

| 层 | 实现 |
|---|---|
| 1. 调用端 | 硬编码 `--approval-mode plan` |
| 2. argv 校验 | `_assert_safety` 在 spawn 前再次扫 argv，拒绝任何被禁标志 |
| 3. Policy whitelist | `policies/readonly.toml` allow `read_file/glob/grep/google_web_search/web_fetch`，deny 所有 write/shell/MCP |
| 4. GEMINI_BIN 路径黑名单 | 拒绝 `/tmp` `/var/tmp` `/dev/shm` 等 world-writable 路径 |
| 5. `--target-dir` 黑名单 | 拒绝 `/` `/etc` `/usr` `$HOME` 过宽路径 |
| 6. `--persist-to` symlink 防护 | `is_symlink()` 拒绝 + `O_NOFOLLOW` 双保险 |

---

## 6. 测试 / 质量

| 维度 | 数值 |
|---|---|
| 单元测试 | **243** 全绿，~0.2s |
| 覆盖率 | `lib/` 整体 **94%** |
| 活调用冒烟 | 4 个 mode 各一份真实 envelope，存 `examples/` |
| Research 模式评测 | 200 条 query 跑过，详见 `docs/test-report.md` |
| Envelope 契约测试 | `tests/contract_test.py` 锁死 schema v1 |
| 安全加固测试 | `tests/test_security_hardening.py` 17 个 case |
| Citation 解析测试 | `tests/test_citations.py` 17 个 case |
| Linting | `ruff check lib bin tests` 无 warning |

---

## 7. 仓库 / 文件全景

```
gemini-bridge/
├── .claude-plugin/
│   ├── plugin.json             # plugin metadata（name, version, license, ...）
│   └── marketplace.json        # 自托管市场（指向自身的 url source）
├── skills/                     # 4 个 thin SKILL.md
│   ├── analyze/SKILL.md
│   ├── research/SKILL.md
│   ├── second-opinion/SKILL.md
│   └── multimodal/SKILL.md
├── bin/ask-gemini              # 共享后端（Python 脚本，无 .py 后缀）
├── lib/                        # 核心模块
│   ├── invoke.py               # build_argv / spawn / 流式 parse
│   ├── fallback.py             # 3 级模型 fallback 状态机
│   ├── preflight.py            # auth / binary / 路径检查 / auto-trust
│   ├── envelope.py             # build_success / build_error
│   ├── persist.py              # --persist-to 落地（symlink 防护）
│   ├── citations.py            # 解析 Gemini grounding redirect URL（v1.1.6+）
│   ├── audit_log.py            # JSONL 审计日志（10 MB 滚动）
│   └── exit_codes.py           # gemini exit code 分类
├── prompts/                    # 每个 mode 一个 .md 模板
│   ├── analyze.md
│   ├── research.md
│   ├── second_opinion.md
│   └── multimodal.md
├── policies/readonly.toml      # allow/deny 白名单
├── tests/                      # 243 测试 + smoke
├── examples/                   # 4 个 mode 各一份真实 envelope
├── evals/                      # research 200 条评测 harness
├── docs/                       # 用户手册 + 设计文档
│   ├── usage.md                # 完整使用手册（4 mode 详解 + env vars + 故障）
│   ├── test-report.md          # 历次测试报告 + bug 复盘
│   ├── implementation-plan.md  # 冻结的设计决策
│   ├── envelope-schema.json    # Schema v1 JSON Schema
│   ├── gemini-cli-reference.md # Gemini CLI 精简参考
│   ├── v2-requirements.md      # v2 需求草稿
│   ├── promotion-drafts.md     # 提交 awesome list / 官方市场的预填文案
│   └── v1-worklog.md           # 本文件
├── CLAUDE.md                   # 给 Claude Code 的工作区指令
├── LICENSE                     # MIT
├── README.md                   # 用户视角主页（357 行）
└── .gitignore                  # 含 testrun.md / message.md / .tmp.md / evals/results/
```

---

## 8. 当前未完成事项

### 8.1 Tier 1 宣传（执行人：用户）

| 渠道 | 何时 | 文案位置 |
|---|---|---|
| Anthropic 官方插件市场 | **任何时候**（用户登录 claude.ai 填表） | `docs/promotion-drafts.md` § A |
| awesome-claude-code | **2026-05-02 起**（仓库须满 1 周；必须 GitHub Web UI 手工提交） | `docs/promotion-drafts.md` § B |

### 8.2 Tier 1 候选（待研究）

- ccplugins/awesome-claude-code-plugins (717 stars，纯 plugin 聚焦)
  - 待研究他们的提交规则（PR 还是 issue）
  - `docs/promotion-drafts.md` § C 留了占位

### 8.3 Tier 2 宣传（推迟）

等 Tier 1 收录后再启动。`docs/promotion-drafts.md` § D 列了清单：Show HN / r/ClaudeAI / 知乎 / 微信 / Twitter thread / 配 GIF demo / dev.to 深度文。

---

## 9. v2 候选项（已记录，不在排期）

详见 `docs/v2-requirements.md`。截至 v1.1.8，最有价值的几个：

| 项 | 价值 | 工作量 |
|---|---|---|
| Source date 解析（fetch HTML 抓 publication date） | 中 | 0.5 天 |
| Source whitelist（`ASK_GEMINI_TRUSTED_DOMAINS=...`） | 中 | 0.5 天 |
| second-opinion 自动检测 "Claude reasoning leaked into --task" | 高 | 1 天（要训练判别 prompt） |
| envelope 加 `quality_score`（基于 sources count / undated ratio） | 中 | 0.5 天 |
| 流式输出（用户要求）的可选 NDJSON 模式 | 低 | 1 天 |
| `--target-files <glob>` 显式列文件，替代自动浏览 | 中 | 0.5 天 |
| 多轮 second-opinion（Gemini ↔ Gemini 互审） | 低 | 1 天 |
| Runner 加 `--rate-limit N/min`（避免高并发触发 quota） | 中 | 0.5 天 |

---

## 10. 经验教训（给 v2 / 给后人）

### 关于 plugin 开发

1. **`marketplace.json` source 形式**：用 `{"source": "url", "url": "https://..."}`。这是 Anthropic 官方 53% plugin 用的、最广泛兼容的形式。`local` 不在官方 schema，别用。
2. **不要相信 `$CLAUDE_PLUGIN_ROOT`**：Claude Code 2.1.x 不一定导出。SKILL.md 用 `find ~/.claude/plugins -path '*<plugin>*/bin/...' -type f` 兜底。
3. **跨平台 binary 路径**：永远用 `shutil.which()` 作为 default，硬编码路径（即使是 Homebrew）只能作为最后 fallback。
4. **Plugin 升级 ≠ Plugin 重装**：Claude Code 2.1.x 的 `marketplace remove + add` 不一定真的清 `installed_plugins.json`。文档要写 troubleshooting。

### 关于开源前的 PII

5. **`evals/results/` 这种运行时产物绝对不能入库**。我们 242 个 envelope 都泄露了 `/Users/cuishengjia/`。`.gitignore` 早期就要写好。
6. **squash 历史**：一个干净 release 之前，squash 整个 git 历史成单 commit。`git log -p` 也会暴露早期 PII。
7. **scoped staging**：永远 `git add <specific-files>`，不要 `git add -A`。我吃过一次亏（v1.1.1 把 tmp 文件推上去）。

### 关于 bug 处理

8. **不要盲信 bug reporter 的 root cause 诊断**。reporter 看到的报错是真的，但他推荐的修复方案（"用 `type` 而不是 `source`"）经验证错的。**用经验数据（160 个真实 plugin）验证理论建议**。
9. **每个 hotfix 后必须有 release notes**，写明：症状、根因（用证据）、修复方式、迁移指南。8 次 release notes 都包含这些字段，给后人清晰路径。
10. **Live testrun > 单元测试**：单元测试全绿不代表 plugin 在用户机器上能跑。v1.0.0 → v1.1.5 的 5 个 install hotfix 都是单元测试发现不了的。`smoke_test.sh` + 真人 testrun 是必须的。

### 关于通信

11. **One question per turn**：用户明确要求过。每次发问只问一个待决策项；多个决策排队。规则在 `~/.claude/rules/common/communication.md`。
12. **Fact-Forcing Gate**：destructive 命令前必须写 (1) 用户请求 (2) 命令产出 (3) 引用用户授权。这是用户配的 PreToolUse hook，不是 plugin 问题。

---

## 11. 命令速查（重装 / 调试 / 测试）

### 完全重装（用户侧）

```bash
# 1. 退出 Claude Code（Ctrl+D）
# 2. 在 shell：
rm -rf ~/.claude/plugins/marketplaces/gemini-bridge ~/.claude/plugins/cache/gemini-bridge*

# 清 stale registry entry（升级时常用）
python3 << 'PY'
import json, shutil
from pathlib import Path
base = Path.home() / ".claude/plugins"
for fname in ["installed_plugins.json", "known_marketplaces.json"]:
    p = base / fname
    if not p.exists():
        continue
    shutil.copy2(p, p.with_suffix(".json.bak"))
    d = json.loads(p.read_text())
    target = d.get("plugins", d) if "plugins" in d else d
    removed = [k for k in list(target.keys()) if "gemini-bridge" in k]
    for k in removed:
        del target[k]
    p.write_text(json.dumps(d, indent=2) + "\n")
    print(f"{fname}: removed {removed}")
PY

# 3. 重启 Claude Code，然后：
# /plugin marketplace add cuishengjia/gemini-bridge
# /plugin install gemini-bridge
```

### 跑单元测试

```bash
cd /Users/cuishengjia/MyAIProjects/GeminiCLI4CC
python3 -m pytest tests/ -q
# 期望：243 passed in ~0.2s
```

### 跑活调用冒烟（消耗 Gemini 配额）

```bash
ASK_GEMINI_LIVE=1 bash tests/smoke_test.sh
```

### 直接 CLI 调用（绕过 Claude）

```bash
ASKGEMINI=$(find ~/.claude/plugins -path '*gemini-bridge*/bin/ask-gemini' -type f -executable | head -1)

# 4 mode 示例
"$ASKGEMINI" --mode analyze --target-dir ~/myproject --prompt "概述项目架构"
"$ASKGEMINI" --mode research --query "Python 3.13 最新发布日期"
"$ASKGEMINI" --mode second-opinion --task "..." --artefact-file ./pr.diff
"$ASKGEMINI" --mode multimodal --image ./screenshot.png --prompt "..."
```

### 发新版的标准动作

```bash
# 1. 改代码 / 文档
# 2. 跑测试
python3 -m pytest tests/ -q

# 3. bump version
# 编辑 .claude-plugin/plugin.json 和 marketplace.json 同步改

# 4. 写 release notes 草稿到 .release-notes-vX.Y.Z.tmp.md
# 5. scoped commit（不要 add -A）
git add .claude-plugin/ <changed paths>
git commit -m "..."

# 6. push + tag + release
git push origin main
git tag -a vX.Y.Z -m "..."
git push origin vX.Y.Z
gh release create vX.Y.Z --title "..." --notes-file .release-notes-vX.Y.Z.tmp.md --latest

# 7. 删 tmp 文件
rm -f .release-notes-vX.Y.Z.tmp.md
```

---

## 12. 关键文件 / 链接索引

| 类别 | 路径 |
|---|---|
| 入口 | `bin/ask-gemini` |
| 调用契约 | `skills/<mode>/SKILL.md` |
| 用户手册 | `docs/usage.md` |
| 架构主线 | `CLAUDE.md` |
| 设计冻结 | `docs/implementation-plan.md` |
| Schema v1 | `docs/envelope-schema.json` |
| 测试报告 | `docs/test-report.md` |
| 提交文案 | `docs/promotion-drafts.md` |
| v2 需求 | `docs/v2-requirements.md` |
| 本文件 | `docs/v1-worklog.md` |

| 外部资源 | URL |
|---|---|
| 仓库 | https://github.com/cuishengjia/gemini-bridge |
| Releases | https://github.com/cuishengjia/gemini-bridge/releases |
| Issues | https://github.com/cuishengjia/gemini-bridge/issues |
| Anthropic plugin docs | https://code.claude.com/docs/en/plugin-marketplaces |
| Gemini CLI | https://geminicli.com |
| Gemini API key | https://aistudio.google.com/apikey |

---

**最后更新**：2026-04-26
**当前 release**：v1.1.8
**主线状态**：✅ 完全闭合，等 Tier 1 提交反馈
