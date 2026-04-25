# ask-gemini-cli v2 需求收集

> 状态：**需求收集中**。v1.0.0 已于 2026-04-22 发版（tag `ask-gemini-cli-v1.0.0`）。
> 在用户明确说"需求收集够了 / 开始 v2"之前，本文件只新增条目，不启动任何实现。

## 使用约定

- 每条需求独立编号（`R-001`, `R-002`, ...）。编号一旦分配就不改、不复用。
- 每条只写最小必要信息。细节讨论放进条目下的 **讨论** 小节，不另起散落文档。
- 状态字段只允许四种：
  - `open` — 刚收录，尚未分析
  - `clarified` — 信息足够开写实现方案
  - `deferred` — 收了但暂不考虑（写明原因）
  - `rejected` — 不做（写明原因）
- 优先级（`P0` / `P1` / `P2` / `P3`）只是当下的主观判断，进入 v2 规划时会重排。
- 来源标签建议值：`user`、`eval`、`incident`、`observation`、`upstream`（Gemini / Claude Code 侧变化）。

## 条目模板

```md
### R-NNN: <一行标题>

- **状态**：open
- **来源**：<user / eval / incident / observation / upstream>
- **提出日期**：YYYY-MM-DD
- **优先级**：P?
- **场景 / 痛点**：<现在是什么情况，哪里不够用>
- **期望行为**：<希望 v2 怎么做>
- **验收信号**：<怎么知道做对了；可测或可观察的标准>
- **影响面**：<会动到哪些模块 / 会不会破坏 Envelope v1 契约>

#### 讨论
（自由文本；每次补充前面加日期）
```

---

## 已收录

### 种子条目（来自 v1 发版后的已知观察，非正式需求）

以下三条是 v1 发版前已经浮现的候选项，挂在这里占位，方便和后续真实需求一起排序。**还没变成正式需求**——用户如果认为重要会升格到 R- 编号。

- 🌱 **runner 层令牌桶 / 速率限制**
  依据：`docs/test-report.md §10.4 / §10.6` —— concurrency=10 引发 quota 风暴（169/200 失败）。
  当前 workaround：手动把 `--concurrency` 调到 2~3。
  可能的形态：`runner.py --rate-limit N/min` + 进程内令牌桶。

- 🌱 **CoT 过滤增强**
  依据：`evals/results/run-20260421-162923/envelopes/q002.json` —— 正文前缀出现 "I will search for..."，P0-1 白名单没兜住。
  可能的形态：扩 `THOUGHT_EVENT_TYPES` 白名单 / 或在 `_parse_events` 里加一层"未知事件类型 → drop"的兜底。

- 🌱 **`evals/datasets/_subsets/` 自动清理**
  依据：失败 agent-team 实验残留；v1 发版前手动清了一次。
  可能的形态：runner 在 `--split` 模式结束后清掉临时切片；或直接加到 `.gitignore`。

---

## 已归档（已做 / 已否 / 过期）

_（暂空）_
