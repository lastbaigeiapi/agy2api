# Antigravity Stealth Gateway (AGY-SG)

A hardened, professional-grade OpenAI-compatible gateway for the Antigravity CLI, engineered for **maximum stealth** and **high-fidelity** automation.

## Stealth Architecture

Unlike simple wrappers, **AGY-SG** implements several layers of obfuscation to ensure that your automated requests are indistinguishable from legitimate human interaction:

1.  **PTY Emulation**: Spawns the CLI inside a virtual pseudo-terminal (PTY). This tricks the application into enabling interactive-only features and bypassing basic script detection.
2.  **Telemetry Scrubbing**: Automatically blocks common tracking and telemetry signals (Sentry, Analytics) at the process level using hardened environment variables.
3.  **Human Jitter**: Implements stochastic timing delays (jitter) to mimic human input cadence and avoid pattern-based detection.
4.  **Session Persistence**: Native support for conversation ID mapping, allowing you to maintain long-running threads without manual intervention.

## Quick Start

```bash
chmod +x run.sh
./run.sh
```

## Advanced Features

### 1. Streaming (SSE)
Supports real-time streaming of response tokens for a low-latency UI experience.

### 2. Multi-Session Mapping
Pass a `user` parameter in your OpenAI request to maintain separate persistent sessions for different users.

```json
{
  "model": "antigravity",
  "messages": [{"role": "user", "content": "Analyze this code."}],
  "user": "user_123"
}
```

## Monitoring

Access the stealth health check:
`GET /health`

> [!WARNING]
> This tool is designed for private, legitimate automation. Use responsibly and in accordance with your organization's security policies.
