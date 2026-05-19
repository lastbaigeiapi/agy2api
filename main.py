#!/usr/bin/env python3
"""
Antigravity Gateway (AGY-GW) - Commercial Edition
A robust, production-ready OpenAI-compatible REST API for the Antigravity CLI.

Features:
- Concurrency Management (Semaphore-based Rate Limiting)
- Session State Persistence (Maps users to agy conversation IDs)
- API Key Authentication
- Real-time SSE Streaming
- Resource-optimized Execution (No TUI scraping)
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from http import HTTPStatus

# --- Configuration ---
PORT = int(os.environ.get("PORT", "8789"))
HOST = os.environ.get("HOST", "0.0.0.0")
AGY_BIN = os.environ.get("AGY_BIN", "agy")
API_KEYS = [k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()]
MAX_CONCURRENT_REQUESTS = int(os.environ.get("MAX_CONCURRENT", "5"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
SESSION_DIR = os.path.expanduser("~/.antigravity_sessions")

os.makedirs(SESSION_DIR, exist_ok=True)

# --- Logging Setup ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AGY-GW")

# --- Concurrency Control ---
# Limits how many agy processes can run simultaneously to prevent OOM
process_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
# Lock to ensure settings.json is not corrupted during concurrent spawns
settings_lock = asyncio.Lock()
SETTINGS_PATH = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")

# --- Core: CLI Executor ---
class AgyExecutor:
    """Safely executes the agy CLI in non-interactive print mode."""
    
    @staticmethod
    async def run_stream(prompt: str, user_id: str, model: str = None):
        """Yields output chunks from the agy process."""
        session_file = os.path.join(SESSION_DIR, f"{user_id}.sid")
        conversation_id = None
        
        # Load previous conversation ID if exists
        if os.path.exists(session_file):
            with open(session_file, "r") as f:
                conversation_id = f.read().strip()

        args = [AGY_BIN, "--print", "--prompt", prompt]
        if conversation_id:
            args.extend(["--conversation", conversation_id])
            
        logger.debug(f"Executing: {' '.join(args)}")
        
        # Stealth environment
        env = os.environ.copy()
        env.update({
            "DO_NOT_TRACK": "1",
            "SENTRY_DSN": "",
            "GOOGLE_ANALYTICS_ID": ""
        })

        async with process_semaphore:
            # Dynamically switch the model in settings.json
            if model and model != "antigravity" and model != "antigravity-commercial":
                async with settings_lock:
                    try:
                        # Read current settings
                        with open(SETTINGS_PATH, "r") as f:
                            settings = json.load(f)
                        
                        # Only write if different
                        if settings.get("model") != model:
                            logger.info(f"Switching engine model to: {model}")
                            settings["model"] = model
                            with open(SETTINGS_PATH, "w") as f:
                                json.dump(settings, f)
                    except Exception as e:
                        logger.error(f"Failed to switch model: {e}")

            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            output_buffer = ""
            while True:
                chunk = await process.stdout.read(1024)
                if not chunk:
                    break
                decoded = chunk.decode('utf-8', errors='ignore')
                output_buffer += decoded
                yield decoded
                
            await process.wait()
            
            if process.returncode != 0:
                err = await process.stderr.read()
                logger.error(f"Agy Process Error: {err.decode('utf-8', 'ignore')}")
            else:
                pass

# --- API Server ---
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

            # Authentication check
            if API_KEYS:
                auth = headers.get("authorization", "")
                token = auth.split("Bearer ")[-1] if "Bearer" in auth else ""
                if token not in API_KEYS:
                    await self.respond_status(HTTPStatus.UNAUTHORIZED, "Invalid API Key")
                    return

            if method == "POST" and path == "/v1/chat/completions":
                body = await self.reader.readexactly(int(headers.get("content-length", 0)))
                await self.handle_chat(json.loads(body))
            elif method == "GET" and path == "/health":
                await self.respond_json({
                    "status": "online", 
                    "engine": "agy-gw-commercial",
                    "concurrency_limit": MAX_CONCURRENT_REQUESTS
                })
            else:
                await self.respond_status(HTTPStatus.NOT_FOUND, "Not Found")
                
        except Exception as e:
            logger.error(f"[{self.request_id}] Server error: {e}")
            try:
                await self.respond_status(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            except:
                pass
        finally:
            self.writer.close()
            await self.writer.wait_closed()

    async def handle_chat(self, req):
        messages = req.get("messages", [])
        prompt = messages[-1]["content"] if messages else ""
        stream = req.get("stream", False)
        user_id = req.get("user", "default_user")
        model = req.get("model", "gemini-3.1-pro-high")
        
        logger.info(f"[{self.request_id}] Req: {prompt[:30]}... (User={user_id}, Model={model}, Stream={stream})")

        if stream:
            await self.stream_response(prompt, user_id, model)
        else:
            await self.block_response(prompt, user_id, model)

    async def block_response(self, prompt, user_id, model):
        full_text = ""
        async for chunk in AgyExecutor.run_stream(prompt, user_id, model):
            full_text += chunk
        
        await self.respond_json({
            "id": f"chatcmpl-{self.request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": full_text.strip()}, "finish_reason": "stop"}]
        })

    async def stream_response(self, prompt, user_id, model):
        self.writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n")
        await self.writer.drain()
        
        async for chunk in AgyExecutor.run_stream(prompt, user_id, model):
            if not chunk: continue
            payload = {
                "id": f"chatcmpl-{self.request_id}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
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

    async def respond_status(self, status, message=""):
        body = json.dumps({"error": {"message": message, "type": "invalid_request_error", "code": status.value}}).encode()
        self.writer.write(f"HTTP/1.1 {status.value} {status.phrase}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
        await self.writer.drain()

async def main():
    server = await asyncio.start_server(lambda r, w: GatewayServer(r, w).serve(), HOST, PORT)
    logger.info(f"AGY-GW Commercial Edition online at {HOST}:{PORT}")
    
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
