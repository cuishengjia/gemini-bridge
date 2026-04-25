# Gemini CLI 参考手册（为 ask-gemini-cli skill 提炼）

> 源：https://geminicli.com/docs/  （抓取日期 2026-04-19）
> 目的：开发 `ask-gemini-cli` skill 所需的完整事实基础。
> 原则：只记 **对从 Claude Code 调用 Gemini CLI 有用** 的内容。

---

## 1. 调用基础

### 1.1 非交互（headless）模式

触发条件（二选一即可）：
- 使用 `-p/--prompt <text>` 标志
- 在非 TTY 环境执行（管道、脚本、CI）

典型管线：
```bash
gemini -p "问题" -o json | jq -r '.response'
cat code.txt | gemini -p "审查这段代码" -o json
git diff | gemini -p "生成提交信息"
```

### 1.2 输出格式 `-o / --output-format`

| 值 | 行为 |
|---|---|
| `text`（默认） | 纯文本 |
| `json` | 单个对象：`{response, stats, error?}` |
| `stream-json` | JSONL，事件类型：`init` / `message` / `tool_use` / `tool_result` / `error` / `result` |

**结构化解析**：`jq -r '.response'` 取主答案；`jq '.stats.models'` 取 token 统计。

### 1.3 Exit codes

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 / API 失败 |
| 41 | 认证失败 |
| 42 | 输入错误（非交互下的无效 prompt/参数） |
| 44 | Sandbox 环境错误 |
| 52 | 配置文件无效 |
| 53 | 超过对话轮数上限 |

---

## 2. 认证

### 2.1 支持方式

| 方式 | 所需环境变量 | Headless 可用 |
|---|---|---|
| Google OAuth（Gemini Code Assist） | 无；浏览器登录 → 缓存到 `~/.gemini/` | ⚠️ 仅当凭证已缓存 |
| Gemini API Key | `GEMINI_API_KEY` | ✅ 最推荐 |
| Vertex AI ADC | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`（先 `gcloud auth application-default login`） | ✅ |
| Vertex AI Service Account | `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | ✅ |
| Vertex AI API Key | `GOOGLE_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | ✅ |

### 2.2 坑

- **`GOOGLE_CLOUD_PROJECT` 已设会强制走组织订阅检查**，可能导致个人账号登录失败。必要时 `env -u GOOGLE_CLOUD_PROJECT gemini ...`。
- **OAuth 用户无 token cache 折扣**（Code Assist API 暂不支持缓存）。成本敏感场景用 API key。
- SSL 拦截（企业网）：`NODE_USE_SYSTEM_CA=1` 或 `NODE_EXTRA_CA_CERTS=<path>`。

---

## 3. 模型

### 3.1 可用模型与别名

| 模型 ID | 别名 | 定位 |
|---|---|---|
| `gemini-3-pro-preview` | `pro`（预览启用时） | 最强推理（preview） |
| `gemini-3-flash-preview` | — | 快速预览 |
| `gemini-2.5-pro` | `pro` | 稳定最强 |
| `gemini-2.5-flash` | `flash` | 稳定快速 |
| `gemini-2.5-flash-lite` | `flash-lite` | 最便宜最快 |
| `auto` | — | 按任务复杂度自动选 |

切换：`gemini -m pro ...` 或 `gemini -m gemini-3-pro-preview ...`。

### 3.2 Model Routing（**关键坑**）

- **默认启用**，由 `ModelAvailabilityService` 监控。
- 触发：配额耗尽 / 服务器错误。
- **行为分叉**：
  - 用户请求：**弹对话框询问** 是否切换 → **headless 下会卡死**
  - 内部调用：`flash-lite → flash → pro` silent fallback
- **对 skill 的含义**：不能依赖 CLI 自动 fallback，必须：
  - 方案 A：调用层自己做 fallback 链（试 pro → flash → flash-lite）
  - 方案 B：使用 `--yolo` 自动接受切换（但会关掉所有批准），不推荐
  - 方案 C：固定 `-m` 不给 fallback 机会，让错误直接返回

### 3.3 `ask-gemini-cli` 推荐 fallback 链

1. `gemini-3-pro-preview`（最强，架构分析/第二意见首选）
2. `gemini-2.5-pro`（preview 额度用完时的稳定替代）
3. `gemini-2.5-flash`（以上都耗尽时的快速降级）
4. ~~`flash-lite`~~：推理能力不足以做分析，跳过。返回"配额耗尽"错误更诚实。

---

## 4. 执行控制

### 4.1 Approval Mode `--approval-mode`

| 值 | 行为 |
|---|---|
| `default` | 工具调用需逐次批准 |
| `auto_edit` | 自动接受 edit 类工具 |
| `yolo` | 自动接受全部（相当于旧 `--yolo`） |
| `plan` | **只读模式**：仅允许读文件、grep、web 查询、写 `.md` 到 plans 目录 |

**`plan` 模式在 headless 下是金标准**：保证 Gemini 绝不会污染我们的项目。

### 4.2 Sandbox `-s/--sandbox`

| 平台 | 技术 |
|---|---|
| macOS | `sandbox-exec`（Seatbelt） |
| Linux | Docker / Podman / gVisor / LXC |
| Windows | 原生 sandbox + `icacls` |

启用方式：`-s` 标志、`GEMINI_SANDBOX=true`、或 `settings.tools.sandbox=true`。自定义容器用 `SANDBOX_FLAGS` 环境变量。

### 4.3 Policy Engine（细粒度授权）

- 取代已废弃的 `--allowed-tools`。
- 位置（优先级从高到低）：
  - Admin：`/etc/gemini-cli/policies/`（Linux） / `/Library/Application Support/GeminiCli/policies/`（macOS）
  - User：`~/.gemini/policies/*.toml`
  - Workspace：`.gemini/policies/*.toml`（默认禁用）
- 格式：TOML，字段 `toolName`, `commandPrefix`, `commandRegex`, `argsPattern`, `decision`, `priority`, `modes`, `mcpName`, `denyMessage`
- CLI：`--policy <path>`, `--admin-policy <path>`

**只读分析策略示例**：
```toml
[[rule]]
toolName = ["read_file", "glob", "grep"]
decision = "allow"
priority = 100

[[rule]]
toolName = "run_shell_command"
decision = "deny"
priority = 500
denyMessage = "Shell disabled for ask-gemini-cli sessions"
```

### 4.4 Trusted Folders

- 默认启用。未信任的文件夹会**禁用** settings、MCP、hooks、custom commands、auto memory、`.env` 加载。
- 信任记录：`~/.gemini/trustedFolders.json`
- 完全关闭：`"security": { "folderTrust": { "enabled": false } }`
- **对 skill 的含义**：若 skill 要调 Gemini 扫描用户项目目录，需预先确保该目录已信任，否则 `.gemini/` 下的配置会被忽略（包括我们的 policy 文件）。

---

## 5. 上下文注入

### 5.1 `--include-directories`

把任意目录挂进 Gemini 的工作区，**这是大上下文分析的核心**：
```bash
gemini -p "审查架构" --include-directories /path/to/repo -o json
```

### 5.2 `GEMINI.md` 上下文文件

- 加载顺序：`~/.gemini/GEMINI.md` → 工作区目录层级 → JIT（工具访问时按祖先目录回溯）
- 可自定义文件名：`settings.context.fileName = ["AGENTS.md", "CONTEXT.md", "GEMINI.md"]`
- 支持 `@./file.md` / `@../shared.md` 导入
- `.agents/` 目录是跨 AI 工具通用别名

### 5.3 `.geminiignore`

- 语法：与 `.gitignore` 一致（glob、`!` 反向、`/` 锚定）
- 位置：项目根
- 典型排除：`node_modules/`, `dist/`, `*.min.js`, 大二进制
- **修改后需重启会话**

### 5.4 `context` 相关 settings

| 键 | 默认 | 说明 |
|---|---|---|
| `context.discoveryMaxDirs` | 200 | 扫描目录数上限 |
| `context.fileFiltering.respectGitIgnore` | true | |
| `context.fileFiltering.respectGeminiIgnore` | true | |
| `context.loadMemoryFromIncludeDirectories` | false | 从 `--include-directories` 读取 memory |

---

## 6. settings.json 速查（与 skill 相关）

位置：
- 用户级：`~/.gemini/settings.json`
- 项目级：`.gemini/settings.json`（项目覆盖用户）

关键键：
```jsonc
{
  "general": {
    "defaultApprovalMode": "plan"        // 推荐 skill 使用时设为 plan
  },
  "output": {
    "format": "json"                      // 默认 JSON 输出
  },
  "model": {
    "name": "gemini-3-pro-preview",      // 默认模型
    "compressionThreshold": 0.5           // 上下文压缩阈值
  },
  "context": {
    "discoveryMaxDirs": 200,
    "fileFiltering": {
      "respectGitIgnore": true,
      "respectGeminiIgnore": true
    }
  },
  "tools": {
    "useRipgrep": true,
    "truncateToolOutputThreshold": 40000
  },
  "security": {
    "folderTrust": { "enabled": true },
    "disableYoloMode": false
  },
  "skills": { "enabled": true },
  "hooksConfig": { "enabled": true }
}
```

**命令行标志优先级 > 项目 settings > 用户 settings > 默认**。

---

## 7. 成本与 Token Caching

### 7.1 免费额度（来自官方说明）

| 认证方式 | 免费上限 |
|---|---|
| 个人 Google（Code Assist） | 1000 请求 / 日 / 用户 |
| Gemini API Key（未付费） | 250 请求 / 日（仅 Flash） |
| Vertex AI Express | 90 天免费试用 |

### 7.2 Token Cache

- **仅 API key / Vertex AI 自动享受**，OAuth 不享受
- 复用 system instructions + 上下文
- 查看：`/stats`（交互）或 JSON 输出的 `stats.models.*.tokens.cached`
- **对 skill 的含义**：反复同题调用同工作区时，用 API key 认证可显著省成本

### 7.3 已观测成本样本

简单 ping 请求（"Reply with one word: pong"）消耗 ~7500 input tokens —— 因为 CLI 会把 system prompt 和工作区元信息自动喂给模型。**不能按裸 prompt 估算成本**。

---

## 8. 子命令（仅列与 skill 开发相关）

### 8.1 `gemini skills`（Gemini 自己的 skill 系统 —— **不是** Claude Code 的）

- 发现路径：`.gemini/skills/`, `.agents/skills/`（项目）→ `~/.gemini/skills/`, `~/.agents/skills/`（用户）
- SKILL.md 需 `name` + `description`，激活机制是 `activate_skill` 工具
- **与 Claude Code skill 的区别**：
  - Claude Code skill 在 `skills/<name>/SKILL.md`
  - Gemini skill 在 `.gemini/skills/<name>/SKILL.md`
  - 两个系统独立运行，我们的 `ask-gemini-cli` 是给 **Claude Code** 用的，放 `skills/`
  - 但可以共用 `.agents/skills/` 跨工具（未来考虑）

### 8.2 `gemini mcp`, `gemini extensions`, `gemini hooks`

对 skill 开发直接影响不大，需要时查官方文档。

---

## 9. 已知常见错误

| 错误 | 原因 | 处置 |
|---|---|---|
| `EADDRINUSE` | 端口冲突 | 杀进程 |
| `MODULE_NOT_FOUND` | 依赖未装 | `npm install -g @google/gemini-cli@latest` |
| `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` | 企业 SSL 拦截 | `NODE_USE_SYSTEM_CA=1` |
| "Location not supported" | 账号所在地区未开放 | 切 API key 或 Vertex |
| 组织订阅检查失败 | `GOOGLE_CLOUD_PROJECT` 有值 | `env -u GOOGLE_CLOUD_PROJECT gemini ...` |
| Headless 下卡住等确认 | Model Routing 提示 / Trust 提示 | 预先信任 + 固定 `-m` + 不依赖 auto fallback |
| CI 环境误触 | `CI_TOKEN` 等变量触发 | `env -u CI_TOKEN gemini ...` |
| IDE Companion warning | IDE 扩展未装 | 无害可忽略，或 `/ide install` |

---

## 10. 对 `ask-gemini-cli` skill 的设计含义（结论）

1. **默认调用模板**：
   ```bash
   gemini \
     --approval-mode plan \
     -m gemini-3-pro-preview \
     -o json \
     --include-directories "$TARGET_DIR" \
     -p "$PROMPT"
   ```
   管道到 `jq -r '.response'` 提取主回答。

2. **认证**：优先 `GEMINI_API_KEY`（env），fallback 到已缓存 OAuth。skill 文档要引导用户导出 key。

3. **Fallback 链**：skill 的 wrapper 脚本自己实现 pro-preview → 2.5-pro → 2.5-flash 的 3 级重试，通过检查 exit code + stderr 决定是否降级。不要依赖 CLI 自动 fallback（headless 会卡）。

4. **安全边界**：强制 `--approval-mode plan`，阻止 Gemini 写文件 / 跑 shell。如需进一步加固，可在 skill 目录附带 policy TOML 并通过 `--policy` 加载。

5. **成本护栏**：skill 必须把 `.stats.models.*.tokens.total` 回传，便于 Claude Code 侧判断是否要改问法或截短上下文。

6. **Trust 预处理**：skill 的 setup 步骤要提示用户一次性信任项目目录（或关闭 `folderTrust`）。

7. **错误传递**：skill wrapper 要检查 exit code，把 41/42/53 等翻译为对 Claude 友好的结构化错误，让 Claude 能做合理降级/重试决策。
