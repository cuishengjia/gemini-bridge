# Promotion Submission Drafts

提交 gemini-bridge 到各类 awesome 列表 / 官方插件市场的预填写文案。**直接复制粘贴**到对应表单字段。

---

## 时间线 / 顺序

| 提交目标 | 何时可提交 | 平台 |
|---|---|---|
| Anthropic 官方插件市场 | **任何时候** | https://claude.ai/settings/plugins/submit |
| awesome-claude-code | **2026-05-02 起**（仓库须满 1 周） | GitHub Web UI 手工提交（`gh` CLI 被禁） |
| ccplugins/awesome-claude-code-plugins | TBD（待研究他们的规则） | https://github.com/ccplugins/awesome-claude-code-plugins |

---

## A. Anthropic 官方插件市场

**URL**: https://claude.ai/settings/plugins/submit

需要 claude.ai 账号登录。具体表单字段不可预知，下面覆盖最常见的所有可能字段；你看到啥就填啥。

### Plugin name

```
gemini-bridge
```

### Tagline / One-liner

```
Read-only bridge from Claude Code to Google Gemini CLI — 4 capabilities Claude can't do natively (1M-token analysis, Google-grounded research, blind cross-model review, multimodal).
```

### Description（长版，~200 词）

```
gemini-bridge exposes four standalone skills that delegate analytical tasks to Google's Gemini CLI from inside Claude Code:

• gemini-bridge:analyze — 1M+ token codebase analysis over whole monorepos
• gemini-bridge:research — Google-grounded research with verified URL citations resolved to real source domains (Bloomberg, Reuters, etc.) rather than opaque grounding redirects
• gemini-bridge:second-opinion — blind critique by a different model lineage with no shared reasoning
• gemini-bridge:multimodal — image / PDF / video frame analysis

Multi-layer read-only enforcement: hardcoded --approval-mode plan, _assert_safety argv re-validation before subprocess spawn, policies/readonly.toml allow/deny whitelist (read tools allow; write/shell/MCP deny), GEMINI_BIN path screen rejecting world-writable temp locations, --target-dir blacklist for system roots, --persist-to symlink protection.

Three-tier model fallback: gemini-3-pro-preview → 2.5-pro → 2.5-flash, only quota/timeout triggers fallback. Frozen envelope schema v1. Zero third-party Python dependencies (stdlib only). 243 unit tests, 94% coverage on lib/. Verified on Linux Claude Code 2.1.119 and macOS 2.1.120.

Prerequisites: Claude Code, Gemini CLI (`npm i -g @google/gemini-cli`), Python 3.11+, Gemini OAuth or API key.
```

### Category（如果有 dropdown）

```
AI Tools / Research / Productivity / Developer Tools
```

任选一个最接近的；表单没出现这些就跳过。

### Repository URL

```
https://github.com/cuishengjia/gemini-bridge
```

### Marketplace install command（如果问）

```
/plugin marketplace add cuishengjia/gemini-bridge
/plugin install gemini-bridge
```

### License

```
MIT
```

### Author / Maintainer

- 名字：`cuishengjia`
- Profile URL：`https://github.com/cuishengjia`

### Tags / Keywords（如果允许）

```
gemini, google-search, codebase-analysis, second-opinion, multimodal, read-only, ai-tools
```

### Screenshot 怎么办

如果表单**强制**要求 screenshot 而我们没有：

- 跳过试试（先看是不是必填）
- 或贴 release 页面 URL：`https://github.com/cuishengjia/gemini-bridge/releases/latest`
- 或临时录一张终端调用 ask-gemini 输出 envelope 的截图

---

## B. awesome-claude-code

**URL**: https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml

⚠️ **必须**：

- 用 **GitHub Web UI** 手工提交（`gh` CLI 会被自动 ban）
- 仓库须满 1 周（2026-05-02 起）
- 之前没有同名提交（提交前先用 search 确认）

### Title

```
[Resource]: gemini-bridge
```

### Display Name

```
gemini-bridge
```

### Category（dropdown）

```
Agent Skills
```

> 维护者注释："I'm currently lumping most things called 'plugins' under 'Agent Skills' until I figure out a better classification system."

### Sub-Category（dropdown）

```
General
```

### Primary Link

```
https://github.com/cuishengjia/gemini-bridge
```

### Author Name

```
cuishengjia
```

### Author Link

```
https://github.com/cuishengjia
```

### License（dropdown）

```
MIT
```

### Description（1-3 句，descriptive, no emojis, no addressing reader）

```
Read-only Claude Code plugin that bridges to Google's Gemini CLI, exposing four mode-specific skills: gemini-bridge:analyze (1M+ token codebase analysis), gemini-bridge:research (Google-grounded research with URL citations resolved to real source domains), gemini-bridge:second-opinion (blind cross-model review), and gemini-bridge:multimodal (image and PDF analysis). Enforces read-only access via Gemini's plan mode plus a policy whitelist, with multi-layer argv validation and a three-tier model fallback chain. 243 unit tests, 94% coverage on lib/, zero third-party Python dependencies.
```

### Validate Claims（plugin 必填）

```
Install via /plugin marketplace add cuishengjia/gemini-bridge then /plugin install gemini-bridge. Prerequisites: Claude Code, Gemini CLI (npm i -g @google/gemini-cli), Python 3.11+, Gemini OAuth or API key. With Gemini auth in place, the four skills are auto-routed by Claude based on conversation context. Read-only enforcement is verifiable from lib/invoke.py:_assert_safety and policies/readonly.toml; citation resolution from lib/citations.py. End-to-end behavior including a 200-query research evaluation is documented in docs/test-report.md.
```

### Specific Task(s)（必填）

```
Ask Claude to research a recent factual question requiring web grounding (e.g., a current stock movement, recent product release, or post-training-cutoff event). Claude should auto-route to gemini-bridge:research and return an envelope containing inline URL citations resolved to real source domains, not vertexaisearch.cloud.google.com redirect tokens.
```

### Specific Prompt(s)（必填）

```
Use Gemini to research Tesla 2026 Q1 delivery numbers — provide the official figures and at least three authoritative source links.
```

### Additional Comments（选填，加分）

```
Plugin distribution uses self-hosted marketplace (the repo IS the marketplace) with marketplace.json source format {"source": "url", "url": "https://github.com/cuishengjia/gemini-bridge.git"} — the canonical pattern used by ~53% of Anthropic's official plugins.

Network behavior: the wrapper makes network requests only to (a) Google AI / Vertex AI via the Gemini CLI subprocess, and (b) HTTP HEAD requests to follow grounding-redirect URLs in the response (lib/citations.py); the latter can be disabled via ASK_GEMINI_NO_RESOLVE_CITATIONS=1. No telemetry, no auto-update, no elevated permissions.

README documents three invocation styles (natural language / slash form / direct CLI), a how-it-works pipeline diagram, and five troubleshooting scenarios with copy-paste fixes.
```

### Checklist（5 项全勾）

- [x] I have checked that this resource hasn't already been submitted
- [x] **It has been over one week since the first public commit to the repo I am recommending** ← 提交日期必须 ≥ 2026-05-02
- [x] All provided links are working and publicly accessible
- [x] I do NOT have any other open issues in this repository
- [x] I am primarily composed of human-y stuff and not electrical circuits

---

## C. ccplugins/awesome-claude-code-plugins（占位，TODO）

**URL**: https://github.com/ccplugins/awesome-claude-code-plugins

717 stars，纯 plugin 聚焦。提交前需研究他们的 CONTRIBUTING.md / issue template，确认提交格式。可能是 PR 形式或 issue 形式。

待研究后补全文案。

---

## D. 其他可考虑的渠道（暂未起草）

| 渠道 | 适合时机 | 形式 |
|---|---|---|
| Show HN | Anthropic 官方收录后 | "Show HN: gemini-bridge — ..." |
| r/ClaudeAI | Stars > 10 后 | Reddit 帖子 |
| 知乎 / 微信公众号 | 中文社区，写"我为啥造这个" | 长文 |
| Dev.to | 国际社区，技术细节文 | 博客文 |
| Twitter/X | 配 GIF / demo 截图 | 5-6 条 thread |

这些进 Tier 2，不在当前 Tier 1 范围内。等 Tier 1 渠道（A + B）有反馈后再启动。

---

## 检查清单（提交前）

每次提交前快速 verify：

- [ ] GitHub repo URL 可访问、最新 release 是 v1.1.8（或更新）
- [ ] README 顶部 badges 都是 green
- [ ] LICENSE 文件存在
- [ ] CLAUDE.md 不包含本机绝对路径或 PII
- [ ] 没有 secrets 残留（`git log -p | grep -i "key\|password\|token"` 应为空）
- [ ] tests 全绿（`python3 -m pytest tests/ -q` 应该 243 passed）
