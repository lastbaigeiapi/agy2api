# Antigravity Gateway (AGY-GW) - Commercial Edition

AGY-GW is a **commercial-grade, high-performance REST API gateway** for the Antigravity CLI. It bridges OpenAI-compatible clients (including OpenClaw, HermesAgent, and regular OpenAI library clients) to the underlying Antigravity intelligence engine.

## Commercial-Grade Features
1. **Concurrency Control (Resource Optimization)**: Spawning terminal processes is resource-intensive. AGY-GW implements a strict asynchronous Semaphore to limit concurrent `agy` executions, preventing memory exhaustion (OOM) under high load. Requests beyond the limit are gracefully queued.
2. **Conversation Transcript Translator**: Automatically translates multi-turn message history (`messages` list) sent by conversational agents into a clean transcript format, prompting the underlying model to naturally reply as the assistant.
3. **OpenClaw & HermesAgent Compatibility**: Support for list-based content formatting (e.g. `[{"type": "text", "text": "..."}]`) commonly sent by advanced agent frameworks.
4. **Smart Model Fallback & Mapping**: Provides mappings from standard OpenAI/Anthropic model names to underlying `agy` engines. Also supports smart fallback logic (resolving names containing `flash`, `mini`, `sonnet`, `opus` to their closest supported match), ensuring out-of-the-box compatibility.
5. **Anti-Infinite-Loop & Auth Fast-Fail**: Monitors `agy` startup and non-blockingly checks for OAuth/authentication prompts within 0.8 seconds. If unauthorized, it terminates the process instantly and returns a `401 Unauthorized` response with setup instructions, preventing infinite client retries and socket hangs.
6. **Telemetry Scrubbing**: Automatically scrubs telemetry environment variables (`SENTRY_DSN`, `DO_NOT_TRACK`) to ensure enterprise data privacy.
7. **Real-time SSE Streaming**: Full support for `stream: true`, delivering tokens as they are generated with sub-second latency.

## Setup & Execution

### Docker Deployment (Recommended)
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

## Configuration (Environment Variables)
- `PORT`: Listen port (default: 8789)
- `HOST`: Listen interface (default: 0.0.0.0)
- `MAX_CONCURRENT`: Maximum number of simultaneous `agy` processes. Tune this based on your server's RAM (default: 5).
- `API_KEYS`: Comma-separated list of valid Bearer tokens (e.g., `sk-123,sk-456`). Leave blank to disable auth.
- `LOG_LEVEL`: Logging verbosity (INFO, DEBUG, ERROR)

## Usage Example

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
