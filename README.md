# Antigravity Gateway (AGY-GW) - Commercial Edition / 企业商用版

[English](#english) | [中文](#chinese)

---

<a name="english"></a>
## English

AGY-GW is a **commercial-grade, high-performance REST API gateway** for the Antigravity CLI. It bridges OpenAI-compatible clients (including OpenClaw, HermesAgent, and regular OpenAI library clients) to the underlying Antigravity intelligence engine.

### Commercial-Grade Features
1. **Concurrency Control (Resource Optimization)**: Spawning terminal processes is resource-intensive. AGY-GW implements a strict asynchronous Semaphore to limit concurrent `agy` executions, preventing memory exhaustion (OOM) under high load. Requests beyond the limit are gracefully queued.
2. **Conversation Transcript Translator**: Automatically translates multi-turn message history (`messages` list) sent by conversational agents into a clean transcript format, prompting the underlying model to naturally reply as the assistant.
3. **OpenClaw & HermesAgent Compatibility**: Support for list-based content formatting (e.g. `[{"type": "text", "text": "..."}]`) commonly sent by advanced agent frameworks.
4. **Smart Model Fallback & Mapping**: Provides mappings from standard OpenAI/Anthropic model names to underlying `agy` engines. Also supports smart fallback logic (resolving names containing `flash`, `mini`, `sonnet`, `opus` to their closest supported match), ensuring out-of-the-box compatibility.
5. **Anti-Infinite-Loop & Auth Fast-Fail**: Monitors `agy` startup and non-blockingly checks for OAuth/authentication prompts within 0.8 seconds. If unauthorized, it terminates the process instantly and returns a `401 Unauthorized` response with setup instructions, preventing infinite client retries and socket hangs.
6. **Telemetry Scrubbing**: Automatically scrubs telemetry environment variables (`SENTRY_DSN`, `DO_NOT_TRACK`) to ensure enterprise data privacy.
7. **Real-time SSE Streaming**: Full support for `stream: true`, delivering tokens as they are generated with sub-second latency.

### Setup & Execution

#### Docker Deployment (Recommended)
1. Build and run the gateway:
   ```bash
   cd /root/agy_gateway
   docker-compose up -d --build
   ```

2. Interactive Authentication:
   If the gateway is unauthenticated or the OAuth token expires, run the helper command inside the container:
   ```bash
   docker exec -it agy-gw-commercial auth
   ```
   Paste the authorization code from the URL and complete the login. The token is stored in the mounted `/root/.gemini` host folder and shared globally.

### Configuration (Environment Variables)
- `PORT`: Listen port (default: 8789)
- `HOST`: Listen interface (default: 0.0.0.0)
- `MAX_CONCURRENT`: Maximum number of simultaneous `agy` processes. Tune this based on your server's RAM (default: 5).
- `API_KEYS`: Comma-separated list of valid Bearer tokens (e.g., `sk-123,sk-456`). Leave blank to disable auth.
- `LOG_LEVEL`: Logging verbosity (INFO, DEBUG, ERROR)

### Usage Example

```bash
curl -N http://127.0.0.1:8789/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-3.1-pro-high",
    "messages": [{"role": "user", "content": "Explain quantum computing in one sentence."}],
    "stream": true
  }'
```

---

<a name="chinese"></a>
## 中文 / Chinese

AGY-GW 是为 Antigravity CLI 设计的**企业级、高性能 REST API 网关**。它无缝连接符合 OpenAI 规范的客户端（包括 OpenClaw、HermesAgent 以及常规的 OpenAI SDK 客户端）至底层的 Antigravity 智能引擎。

### 企业级特性
1. **并发控制与资源优化**：生成终端进程非常消耗系统资源。AGY-GW 实现了严格的异步信号量（Semaphore）限制并发 `agy` 执行量，防止高负载下内存溢出（OOM），超出并发限制的请求会自动进入队列优雅等待。
2. **多轮对话翻译器**：自动将对话智能体发送的多轮历史记录（`messages` 列表）翻译成规范的聊天剧本，引导底层模型以 Assistant 角色进行自然且符合语境的回复。
3. **OpenClaw & HermesAgent 完美兼容**：全面支持复杂智能体框架常用的列表格式消息内容（例如 `[{"type": "text", "text": "..."}]`），防止解析异常。
4. **智能模型退避与映射**：内置通用 OpenAI/Anthropic 模型到 `agy` 支持引擎的映射表，并支持智能包含匹配（如自动将含有 `flash`、`mini`、`sonnet`、`opus` 等关键字的请求导向最贴近的可用模型），确保完全开箱即用。
5. **防止重试死循环与未授权熔断**：在 `agy` 启动时非阻塞监控 stdout。若在 0.8 秒内检测到 OAuth 或未授权提示，将**立即强制终止**进程，并向客户端秒级返回 `401 Unauthorized` 及交互授权指导，彻底杜绝无谓的客户端重试循环与配额浪费。
6. **遥测净化**：自动屏蔽和净化 `SENTRY_DSN` 和 `DO_NOT_TRACK` 等遥测环境变量，保证企业数据隐私。
7. **实时 SSE 流式传输**：完美支持 `stream: true`，以亚秒级延迟实时推送生成的 Token。

### 部署与使用

#### Docker 部署（推荐）
1. 构建并运行网关：
   ```bash
   cd /root/agy_gateway
   docker-compose up -d --build
   ```

2. 交互式授权：
   如果网关提示未授权或 OAuth Token 过期，只需在宿主机终端中执行：
   ```bash
   docker exec -it agy-gw-commercial auth
   ```
   访问打印出的链接并复制授权码，贴回终端即可完成登录。Token 会保存在宿主机的 `/root/.gemini` 目录下并全局共享给容器。

### 配置说明（环境变量）
- `PORT`：网关监听端口（默认：8789）
- `HOST`：监听网卡地址（默认：0.0.0.0）
- `MAX_CONCURRENT`：最大同时允许运行的 `agy` 进程数。请根据服务器内存进行微调（默认：5）。
- `API_KEYS`：以英文逗号分隔的合法 Bearer 令牌列表（例如 `sk-123,sk-456`）。留空则关闭网关鉴权。
- `LOG_LEVEL`：日志级别（INFO, DEBUG, ERROR）

### 调用示例

```bash
curl -N http://127.0.0.1:8789/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-3.1-pro-high",
    "messages": [{"role": "user", "content": "用一句话解释什么是量子计算。"}],
    "stream": true
  }'
```
