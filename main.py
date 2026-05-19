#!/usr/bin/env python3
"""
Antigravity Stealth Gateway (AGY-SG)
A hardened, professional OpenAI-compatible gateway for Antigravity CLI.

Designed for stealth, reliability, and high-fidelity output.
"""

import asyncio
import json
import os
import pty
import random
import sys
import time
import uuid
import signal
from http import HTTPStatus

# --- Configuration ---
PORT = int(os.environ.get("PORT", "8789"))
HOST = os.environ.get("HOST", "0.0.0.0")
AGY_BIN = os.environ.get("AGY_BIN", "agy")
SESSION_DIR = os.path.expanduser("~/.antigravity_sessions")

# --- Stealth Environment ---
STEALTH_ENV = os.environ.copy()
STEALTH_ENV.update({
    "DO_NOT_TRACK": "1",
    "SENTRY_DSN": "",
    "GOOGLE_ANALYTICS_ID": "",
    "TERM": "xterm-256color",  # Mimic a real terminal
    "PAGER": "cat",
})

os.makedirs(SESSION_DIR, exist_ok=True)

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

class StealthWrapper:
    """Executes agy in a pseudo-terminal for maximum stealth."""
    
    @staticmethod
    async def run(prompt, conversation_id=None, model_hint=None):
        """Spawns agy in a PTY and streams its output."""
        
        # Add a small human-like jitter (100ms - 400ms)
        await asyncio.sleep(random.uniform(0.1, 0.4))
        
        args = [AGY_BIN, "--print", "--prompt", prompt]
        if conversation_id:
            args.extend(["--conversation", conversation_id])
        
        log(f"Spawning PTY: {' '.join(args)}")
        
        master_fd, slave_fd = pty.openpty()
        
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=STEALTH_ENV,
            preexec_fn=os.setsid
        )
        
        os.close(slave_fd)
        
        # Stream from the PTY master
        loop = asyncio.get_running_loop()
        output = b""
        
        while True:
            try:
                # Read from PTY master
                # We use a wrapper to make it non-blocking
                data = await loop.run_in_executor(None, os.read, master_fd, 1024)
                if not data: break
                
                output += data
                # Strip TTY escape codes if any (optional, but cleaner)
                clean_chunk = data.decode('utf-8', errors='ignore')
                yield clean_chunk
                
            except OSError:
                break

        os.close(master_fd)
        await process.wait()
        
        if process.returncode != 0:
            log(f"Process exited with code {process.returncode}")

class GatewayServer:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.request_id = str(uuid.uuid4())

    async def serve(self):
        try:
            line = await self.reader.readline()
            if not line: return
            
            method, path, _ = line.decode().split()
            headers = {}
            while True:
                line = await self.reader.readline()
                if line == b"\r\n" or not line: break
                k, v = line.decode().split(":", 1)
                headers[k.strip().lower()] = v.strip()

            if method == "POST" and path == "/v1/chat/completions":
                body = await self.reader.readexactly(int(headers.get("content-length", 0)))
                await self.handle_chat(json.loads(body))
            elif method == "GET" and path == "/health":
                await self.respond_json({"status": "stealth_active", "engine": "agy-sg"})
            else:
                await self.respond_status(HTTPStatus.NOT_FOUND)
                
        except Exception as e:
            log(f"[{self.request_id}] Server error: {e}")
        finally:
            self.writer.close()
            await self.writer.wait_closed()

    async def handle_chat(self, req):
        messages = req.get("messages", [])
        prompt = messages[-1]["content"] if messages else ""
        stream = req.get("stream", False)
        user_id = req.get("user", "default_user")
        
        # Session Persistence
        session_file = os.path.join(SESSION_DIR, f"{user_id}.sid")
        conv_id = None
        if os.path.exists(session_file):
            with open(session_file, "r") as f:
                conv_id = f.read().strip()

        log(f"[{self.request_id}] Req: {prompt[:30]}... (Stream={stream}, Session={conv_id})")

        if stream:
            await self.stream_response(prompt, conv_id)
        else:
            await self.block_response(prompt, conv_id)

    async def block_response(self, prompt, conv_id):
        full_text = ""
        async for chunk in StealthWrapper.run(prompt, conv_id):
            full_text += chunk
        
        await self.respond_json({
            "id": f"chatcmpl-{self.request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "antigravity-stealth",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": full_text}, "finish_reason": "stop"}]
        })

    async def stream_response(self, prompt, conv_id):
        self.writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n")
        await self.writer.drain()
        
        async for chunk in StealthWrapper.run(prompt, conv_id):
            payload = {
                "id": f"chatcmpl-{self.request_id}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "antigravity-stealth",
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]
            }
            self.writer.write(f"data: {json.dumps(payload)}\n\n".encode())
            await self.writer.drain()
        
        self.writer.write(b"data: [DONE]\n\n")
        await self.writer.drain()

    async def respond_json(self, data):
        body = json.dumps(data).encode()
        resp = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
        self.writer.write(resp)
        await self.writer.drain()

    async def respond_status(self, status):
        self.writer.write(f"HTTP/1.1 {status.value} {status.phrase}\r\n\r\n".encode())
        await self.writer.drain()

async def main():
    server = await asyncio.start_server(lambda r, w: GatewayServer(r, w).serve(), HOST, PORT)
    log(f"Antigravity Stealth Gateway (AGY-SG) online at {HOST}:{PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
