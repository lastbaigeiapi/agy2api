# Antigravity Gateway (AGY-GW) - Commercial Edition

AGY-GW is a **commercial-grade, high-performance REST API gateway** for the Antigravity CLI. It bridges OpenAI-compatible clients to the underlying Antigravity intelligence engine.

## Commercial-Grade Features
1. **Concurrency Control (Resource Optimization)**: Spawning terminal processes is resource-intensive. AGY-GW implements a strict asynchronous Semaphore to limit concurrent `agy` executions, preventing memory exhaustion (OOM) under high load. Requests beyond the limit are gracefully queued.
2. **Session Persistence**: Maintains context across stateless API calls. By passing a `user` parameter in your payload, the gateway automatically maps API requests to persistent Antigravity Conversation IDs using `--continue`.
3. **API Key Authentication**: Built-in Bearer token validation protects your endpoint from unauthorized access.
4. **Real-time SSE Streaming**: Full support for `stream: true`, delivering tokens as they are generated with sub-second latency.
5. **Telemetry Scrubbing**: Automatically scrubs telemetry environment variables (`SENTRY_DSN`, `DO_NOT_TRACK`) to ensure enterprise data privacy.

## Setup & Execution

```bash
chmod +x run.sh
./run.sh
```

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
    "model": "antigravity",
    "messages": [{"role": "user", "content": "Explain quantum computing in one sentence."}],
    "user": "client_abc_123",
    "stream": true
  }'
```
