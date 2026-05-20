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
import select
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
    "gemini-3.1-pro-high": "gemini-3.1-pro",
    "gemini-3.5-flash-high": "gemini-2.5-flash",
    "claude-4-5-sonnet": "claude-3-5-sonnet",
    "claude-opus-4-6": "claude-3-opus",
    "google-jarvis-v4s": "google-jarvis-v4s",

    # Common OpenAI / Anthropic client fallbacks
    "gpt-4-turbo": "gemini-3.1-pro",
    "gpt-4": "gemini-3.1-pro",
    "gpt-4o": "gemini-3.1-pro",
    "gpt-4o-mini": "gemini-2.5-flash",
    "gpt-3.5-turbo": "gemini-2.5-flash",
    "claude-3-5-sonnet": "claude-3-5-sonnet",
    "claude-3-opus": "claude-3-opus",
    "claude-3-haiku": "gemini-2.5-flash",
    "pro": "gemini-3.1-pro",
    "flash": "gemini-2.5-flash",
}

def switch_model(model: str):
    """Hot-swap the model in settings.json with smart fallback."""
    if not model or model in ("antigravity", "antigravity-commercial"):
        return
    
    # Resolve standard key to real model, fallback to model name substring check, then default to gemini-2.5-pro
    target_model = MODEL_MAP.get(model)
    if not target_model:
        model_lower = model.lower()
        if "flash" in model_lower or "mini" in model_lower or "turbo" in model_lower or "3.5" in model_lower or "lite" in model_lower:
            target_model = "gemini-2.5-flash"
        elif "sonnet" in model_lower:
            target_model = "claude-3-5-sonnet"
        elif "opus" in model_lower:
            target_model = "claude-3-opus"
        elif "jarvis" in model_lower:
            target_model = "google-jarvis-v4s"
        elif "pro" in model_lower or "3.1" in model_lower:
            target_model = "gemini-3.1-pro"
        else:
            target_model = "gemini-2.5-pro"  # Robust default fallback

    with _settings_lock:
        try:
            with open(SETTINGS_PATH, "r") as f:
                settings = json.load(f)
            current = settings.get("model")
            if current != target_model:
                logger.info(f"Switching model: {current} -> {target_model} (requested: {model})")
                settings["model"] = target_model
                with open(SETTINGS_PATH, "w") as f:
                    json.dump(settings, f)
        except Exception as e:
            logger.error(f"Model switch failed: {e}")

def spawn_agy_process(args, env):
    """Spawns agy process and checks for authentication prompts within 0.8 seconds."""
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd="/root",
    )
    
    # Wait up to 0.8 seconds for initial stdout data using select
    rlist, _, _ = select.select([proc.stdout], [], [], 0.8)
    if rlist:
        # Check the first line of stdout
        first_line_bytes = proc.stdout.readline()
        first_line = first_line_bytes.decode("utf-8", errors="ignore")
        if "Authentication required" in first_line or "Waiting for authentication" in first_line or "visit" in first_line or "auth" in first_line.lower():
            proc.terminate()
            proc.wait()
            raise PermissionError(
                "Antigravity Gateway is not authenticated. "
                "Please run 'docker exec -it agy-gw-commercial auth' in your host terminal to authenticate."
            )
        # Return proc and the first line we already read so it doesn't get lost
        return proc, first_line_bytes
    
    # Check if process exited with error immediately
    if proc.poll() is not None and proc.returncode != 0:
        stderr_output = proc.stderr.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"agy process exited immediately with code {proc.returncode}: {stderr_output}")
        
    return proc, b""

def run_agy(prompt: str, model: str = None):
    """Execute agy --print synchronously and return the output."""
    switch_model(model)

    env = os.environ.copy()
    env.update({
        "DO_NOT_TRACK": "1",
        "SENTRY_DSN": "",
        "GOOGLE_ANALYTICS_ID": "",
        "SSH_CLIENT": "127.0.0.1 1 1",
    })

    if not isinstance(prompt, str):
        prompt = str(prompt)

    args = [AGY_BIN, "--print", prompt]
    logger.debug(f"Exec: {' '.join(args)}")

    _semaphore.acquire()
    try:
        proc, first_line_bytes = spawn_agy_process(args, env)
        stdout_output = first_line_bytes.decode("utf-8", errors="ignore")
        stdout_output += proc.stdout.read().decode("utf-8", errors="ignore")
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", errors="ignore")
            logger.error(f"agy stderr: {err[:500]}")
        return stdout_output.strip()
    except PermissionError as e:
        logger.error(f"Auth error: {e}")
        return f"[Error] {e}"
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
        "SSH_CLIENT": "127.0.0.1 1 1",
    })

    if not isinstance(prompt, str):
        prompt = str(prompt)

    args = [AGY_BIN, "--print", prompt]
    logger.debug(f"Exec (stream): {' '.join(args)}")

    _semaphore.acquire()
    try:
        proc, first_line_bytes = spawn_agy_process(args, env)
        if first_line_bytes:
            yield first_line_bytes.decode("utf-8", errors="ignore")
        for chunk in iter(lambda: proc.stdout.read(512), b""):
            yield chunk.decode("utf-8", errors="ignore")
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", "ignore")
            logger.error(f"agy stderr: {err[:500]}")
    except PermissionError as e:
        logger.error(f"Auth error in stream: {e}")
        yield f"[Error] {e}"
    except Exception as e:
        logger.error(f"agy stream error: {e}")
        yield f"[Error] {e}"
    finally:
        _semaphore.release()


def split_thinking_text(text: str):
    """Splits full response text into (reasoning_content, content) if it contains <think>...</think>."""
    if not text:
        return None, ""
    
    start_tag = "<think>"
    end_tag = "</think>"
    
    start_idx = text.find(start_tag)
    if start_idx != -1:
        end_idx = text.find(end_tag, start_idx + len(start_tag))
        if end_idx != -1:
            reasoning = text[start_idx + len(start_tag):end_idx]
            content = text[:start_idx] + text[end_idx + len(end_tag):]
            return reasoning.strip(), content.strip()
        else:
            reasoning = text[start_idx + len(start_tag):]
            content = text[:start_idx]
            return reasoning.strip(), content.strip()
            
    return None, text

def parse_thinking_stream(generator):
    """
    Parses a stream of text chunks, detecting <think> and </think> tags,
    yielding tuples of (field_name, text) where field_name is either
    'reasoning_content' or 'content'.
    """
    state = "content"
    buffer = ""
    
    for chunk in generator:
        buffer += chunk
        
        while buffer:
            if state == "content":
                idx = buffer.find("<think>")
                if idx != -1:
                    text_before = buffer[:idx]
                    if text_before:
                        yield "content", text_before
                    buffer = buffer[idx + 7:]
                    state = "reasoning"
                else:
                    # Check for partial <think> tag
                    partial_len = 0
                    for i in range(1, min(7, len(buffer) + 1)):
                        suffix = buffer[-i:]
                        if "<think>".startswith(suffix):
                            partial_len = i
                    if partial_len > 0:
                        text_to_yield = buffer[:-partial_len]
                        buffer = buffer[-partial_len:]
                    else:
                        text_to_yield = buffer
                        buffer = ""
                    if text_to_yield:
                        yield "content", text_to_yield
                    if buffer and not text_to_yield:
                        break
            elif state == "reasoning":
                idx = buffer.find("</think>")
                if idx != -1:
                    text_before = buffer[:idx]
                    if text_before:
                        yield "reasoning_content", text_before
                    buffer = buffer[idx + 8:]
                    state = "content"
                else:
                    # Check for partial </think> tag
                    partial_len = 0
                    for i in range(1, min(8, len(buffer) + 1)):
                        suffix = buffer[-i:]
                        if "</think>".startswith(suffix):
                            partial_len = i
                    if partial_len > 0:
                        text_to_yield = buffer[:-partial_len]
                        buffer = buffer[-partial_len:]
                    else:
                        text_to_yield = buffer
                        buffer = ""
                    if text_to_yield:
                        yield "reasoning_content", text_to_yield
                    if buffer and not text_to_yield:
                        break
    if buffer:
        yield "content" if state == "content" else "reasoning_content", buffer


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
        
        # Build prompt from messages history
        formatted_prompt = ""
        last_message_text = ""
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Parse content if list/array
            text_content = ""
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            parts.append(part.get("text", ""))
                        elif "text" in part:
                            parts.append(part["text"])
                    elif isinstance(part, str):
                        parts.append(part)
                text_content = "".join(parts)
            else:
                text_content = str(content)
            
            last_message_text = text_content
            
            role_capitalized = role.capitalize()
            if role == "system":
                formatted_prompt += f"Instructions: {text_content}\n\n"
            else:
                formatted_prompt += f"{role_capitalized}: {text_content}\n"
        
        if len(messages) > 1:
            # Multi-turn conversation: prompt model to reply as assistant
            formatted_prompt += "Assistant: "
            prompt = formatted_prompt
        else:
            # Single-turn conversation: pass text-content directly as-is
            prompt = last_message_text

        stream = body.get("stream", False)
        model = body.get("model", "gemini-3.1-pro-high")
        req_id = str(uuid.uuid4())[:8]

        # Log prompt safely
        logged_prompt = prompt.replace("\n", " ")
        logger.info(f"[{req_id}] Model={model} Stream={stream} Prompt={logged_prompt[:40]}...")

        if stream:
            self._handle_stream(req_id, prompt, model)
        else:
            self._handle_block(req_id, prompt, model)

    def _handle_block(self, req_id, prompt, model):
        output = run_agy(prompt, model)
        reasoning_content, content = split_thinking_text(output)
        
        prompt_tokens = len(prompt) // 4
        completion_tokens = len(output) // 4
        total_tokens = prompt_tokens + completion_tokens
        
        message = {"role": "assistant", "content": content}
        if reasoning_content:
            message["reasoning_content"] = reasoning_content

        self._send_json(200, {
            "id": f"chatcmpl-{req_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total_tokens}
        })

    def _handle_stream(self, req_id, prompt, model):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        prompt_tokens = len(prompt) // 4
        completion_len = 0

        # Parse stream using helper to dynamically separate thinking from final content
        for field_name, text in parse_thinking_stream(run_agy_stream(prompt, model)):
            if not text:
                continue
            completion_len += len(text)
            payload = {
                "id": f"chatcmpl-{req_id}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {field_name: text},
                    "finish_reason": None
                }]
            }
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        completion_tokens = completion_len // 4
        total_tokens = prompt_tokens + completion_tokens

        # Send usage chunk before final stop
        usage_payload = {
            "id": f"chatcmpl-{req_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total_tokens}
        }
        self.wfile.write(f"data: {json.dumps(usage_payload)}\n\n".encode())

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
        self.close_connection = True


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
