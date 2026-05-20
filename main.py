#!/usr/bin/env python3
"""
Antigravity Gateway (AGY-GW) - Commercial Edition
Production-ready OpenAI-compatible REST API for the Antigravity CLI.
Uses stdlib http.server for maximum stability (zero external dependencies).
"""

import asyncio
import json
import logging
import os
import re
import signal
import sys
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import subprocess
import threading

# --- Configuration ---
PORT = int(os.environ.get("PORT", "8789"))
HOST = os.environ.get("HOST", "0.0.0.0")
AGY_BIN = os.environ.get("AGY_BIN", "agy")
API_KEYS = [k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()]
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "5"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
SETTINGS_PATH = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")

# --- Logging ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AGY-GW")

# --- Concurrency ---
_semaphore = threading.Semaphore(MAX_CONCURRENT)
_settings_lock = threading.Lock()

# --- Model Mapping ---
# Maps OpenAI-style model names to agy internal model identifiers
MODEL_MAP = {
    "gemini-3.1-pro-high": "gemini-2.5-pro",
    "gemini-3.5-flash-high": "gemini-2.5-flash",
    "claude-4-5-sonnet": "claude-3-5-sonnet",
    "claude-opus-4-6": "claude-3-opus",
    "google-jarvis-v4s": "google-jarvis-v4s",
    # Pass-through: if not in map, use as-is
}

def switch_model(model: str):
    """Hot-swap the model in settings.json."""
    if not model or model in ("antigravity", "antigravity-commercial"):
        return
    with _settings_lock:
        try:
            with open(SETTINGS_PATH, "r") as f:
                settings = json.load(f)
            current = settings.get("model")
            if current != model:
                logger.info(f"Switching model: {current} -> {model}")
                settings["model"] = model
                with open(SETTINGS_PATH, "w") as f:
                    json.dump(settings, f)
        except Exception as e:
            logger.error(f"Model switch failed: {e}")

def run_agy(prompt: str, model: str = None):
    """Execute agy --print synchronously and return the output."""
    switch_model(model)

    env = os.environ.copy()
    env.update({
        "DO_NOT_TRACK": "1",
        "SENTRY_DSN": "",
        "GOOGLE_ANALYTICS_ID": "",
    })

    args = [AGY_BIN, "--print", prompt]
    logger.debug(f"Exec: {' '.join(args)}")

    _semaphore.acquire()
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        if proc.returncode != 0:
            logger.error(f"agy stderr: {proc.stderr[:500]}")
        return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error("agy process timed out (300s)")
        return "[Error] Request timed out."
    except Exception as e:
        logger.error(f"agy exec error: {e}")
        return f"[Error] {e}"
    finally:
        _semaphore.release()

def run_agy_stream(prompt: str, model: str = None):
    """Execute agy --print and yield output chunks as they arrive."""
    switch_model(model)

    env = os.environ.copy()
    env.update({
        "DO_NOT_TRACK": "1",
        "SENTRY_DSN": "",
        "GOOGLE_ANALYTICS_ID": "",
    })

    args = [AGY_BIN, "--print", prompt]
    logger.debug(f"Exec (stream): {' '.join(args)}")

    _semaphore.acquire()
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        for chunk in iter(lambda: proc.stdout.read(512), b""):
            yield chunk.decode("utf-8", errors="ignore")
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", "ignore")
            logger.error(f"agy stderr: {err[:500]}")
    except Exception as e:
        logger.error(f"agy stream error: {e}")
        yield f"[Error] {e}"
    finally:
        _semaphore.release()


class GatewayHandler(BaseHTTPRequestHandler):
    """Handles OpenAI-compatible API requests."""

    # Suppress default stderr logging per-request
    def log_message(self, fmt, *args):
        logger.debug(fmt % args)

    def _send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self):
        if not API_KEYS:
            return True
        auth = self.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        if token in API_KEYS:
            return True
        self._send_json(401, {"error": {"message": "Invalid API Key", "type": "auth_error", "code": 401}})
        return False

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {
                "status": "online",
                "engine": "agy-gw-commercial",
                "concurrency_limit": MAX_CONCURRENT,
            })
        elif self.path == "/v1/models":
            models = [
                {"id": m, "object": "model", "owned_by": "antigravity"}
                for m in MODEL_MAP
            ]
            self._send_json(200, {"object": "list", "data": models})
        else:
            self._send_json(404, {"error": {"message": "Not Found"}})

    def do_POST(self):
        if not self._check_auth():
            return

        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": "Not Found"}})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        messages = body.get("messages", [])
        prompt = messages[-1]["content"] if messages else ""
        stream = body.get("stream", False)
        model = body.get("model", "gemini-3.1-pro-high")
        req_id = str(uuid.uuid4())[:8]

        logger.info(f"[{req_id}] Model={model} Stream={stream} Prompt={prompt[:40]}...")

        if stream:
            self._handle_stream(req_id, prompt, model)
        else:
            self._handle_block(req_id, prompt, model)

    def _handle_block(self, req_id, prompt, model):
        output = run_agy(prompt, model)
        self._send_json(200, {
            "id": f"chatcmpl-{req_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": output},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        })

    def _handle_stream(self, req_id, prompt, model):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        for chunk in run_agy_stream(prompt, model):
            if not chunk:
                continue
            payload = {
                "id": f"chatcmpl-{req_id}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None
                }]
            }
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        # Send final stop chunk
        stop_payload = {
            "id": f"chatcmpl-{req_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        self.wfile.write(f"data: {json.dumps(stop_payload)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Thread-per-request HTTP server for concurrent handling."""
    allow_reuse_address = True
    daemon_threads = True


def main():
    server = ThreadedHTTPServer((HOST, PORT), GatewayHandler)
    logger.info(f"AGY-GW Commercial Edition online at http://{HOST}:{PORT}")
    logger.info(f"Concurrency limit: {MAX_CONCURRENT} | Auth: {'enabled' if API_KEYS else 'disabled'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
