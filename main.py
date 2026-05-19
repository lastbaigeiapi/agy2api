#!/usr/bin/env python3
"""
Antigravity Gateway (AGY-GW)
A high-performance, streaming-capable OpenAI-compatible gateway for Antigravity CLI.

Features:
- Full Async/Await architecture.
- Real-time streaming support (Server-Sent Events).
- Transparent CLI wrapping.
- Custom model routing.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from http import HTTPStatus

# --- Configuration ---
PORT = int(os.environ.get("PORT", "8789"))
HOST = os.environ.get("HOST", "0.0.0.0")
AGY_BIN = os.environ.get("AGY_BIN", "agy")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

class AntigravityWrapper:
    """Manages the execution and streaming of the agy CLI."""
    
    @staticmethod
    async def execute_stream(prompt, model_hint=None):
        """Executes agy and yields chunks of its output."""
        # Note: We can expand this to include --continue for session persistence
        cmd = [AGY_BIN, "--print", "--prompt", prompt]
        
        log(f"Spawning: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Stream stdout line by line
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode('utf-8')

        await process.wait()
        if process.returncode != 0:
            err = await process.stderr.read()
            log(f"Error: {err.decode('utf-8')}")

class GatewayHandler:
    """Minimal Async HTTP Handler."""
    
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    async def handle(self):
        try:
            request_data = await self.reader.readuntil(b"\r\n\r\n")
            header_lines = request_data.decode().split("\r\n")
            first_line = header_lines[0].split()
            if not first_line: return
            
            method, path = first_line[0], first_line[1]
            
            if method == "POST" and path == "/v1/chat/completions":
                await self.process_completions(header_lines)
            elif method == "GET" and path == "/health":
                await self.send_json({"status": "healthy"})
            else:
                await self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as e:
            log(f"Handler error: {e}")
        finally:
            self.writer.close()
            await self.writer.wait_closed()

    async def process_completions(self, headers):
        # Extract content length
        content_length = 0
        for h in headers:
            if h.lower().startswith("content-length:"):
                content_length = int(h.split(":")[1].strip())
        
        body = await self.reader.readexactly(content_length)
        data = json.loads(body)
        
        messages = data.get("messages", [])
        prompt = messages[-1]["content"] if messages else ""
        stream = data.get("stream", False)
        model = data.get("model", "gemini-3.5-flash-high")

        if stream:
            await self.handle_streaming_response(prompt, model)
        else:
            await self.handle_blocking_response(prompt, model)

    async def handle_blocking_response(self, prompt, model):
        content = ""
        async for chunk in AntigravityWrapper.execute_stream(prompt, model):
            content += chunk
        
        response = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]
        }
        await self.send_json(response)

    async def handle_streaming_response(self, prompt, model):
        # Send headers for SSE
        headers = [
            "HTTP/1.1 200 OK",
            "Content-Type: text/event-stream",
            "Cache-Control: no-cache",
            "Connection: keep-alive",
            "\r\n"
        ]
        self.writer.write("\r\n".join(headers).encode())
        await self.writer.drain()

        request_id = f"chatcmpl-{uuid.uuid4()}"
        
        async for chunk in AntigravityWrapper.execute_stream(prompt, model):
            payload = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]
            }
            self.writer.write(f"data: {json.dumps(payload)}\n\n".encode())
            await self.writer.drain()

        # End of stream
        self.writer.write(b"data: [DONE]\n\n")
        await self.writer.drain()

    async def send_json(self, data):
        body = json.dumps(data).encode()
        headers = [
            "HTTP/1.1 200 OK",
            "Content-Type: application/json",
            f"Content-Length: {len(body)}",
            "\r\n"
        ]
        self.writer.write("\r\n".join(headers).encode() + body)
        await self.writer.drain()

    async def send_error(self, status):
        self.writer.write(f"HTTP/1.1 {status.value} {status.phrase}\r\n\r\n".encode())
        await self.writer.drain()

async def main():
    server = await asyncio.start_server(
        lambda r, w: GatewayHandler(r, w).handle(),
        HOST, PORT
    )
    log(f"Antigravity Gateway running on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
