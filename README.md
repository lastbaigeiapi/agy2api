# Antigravity Gateway (AGY-GW)

A modern, high-performance OpenAI-compatible gateway for the Antigravity CLI. 

> [!NOTE]
> This is a complete rewrite from the ground up, built for speed and robustness.

## Features

- **Asynchronous Engine**: Built on Python's `asyncio` for maximum concurrency.
- **Real-time Streaming**: Supports OpenAI-compatible Server-Sent Events (SSE).
- **Direct CLI Integration**: Wraps the `agy` CLI natively, no proxying required.
- **Zero Dependencies**: Runs on standard Python 3.11+.

## Setup

```bash
chmod +x run.sh
./run.sh
```

## Usage

### Standard Completion
```bash
curl http://127.0.0.1:8789/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [{"role": "user", "content": "How are you?"}]
  }'
```

### Streaming Completion
```bash
curl http://127.0.0.1:8789/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [{"role": "user", "content": "Write a long story."}],
    "stream": true
  }'
```

## Monitoring

You can use the health check endpoint to verify the server status:
`GET /health`
