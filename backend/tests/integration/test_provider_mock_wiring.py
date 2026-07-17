# backend/tests/integration/test_provider_mock_wiring.py
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from backend.tests.integration.test_provider_resilience import FakeProviderServer


ANTHROPIC_OK = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "fake",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}

SSE_CHUNKS = [
    {"id": "c1", "object": "chat.completion.chunk", "model": "fake",
     "choices": [{"index": 0, "delta": {"content": "he"}, "finish_reason": None}]},
    {"id": "c1", "object": "chat.completion.chunk", "model": "fake",
     "choices": [{"index": 0, "delta": {"content": "llo"}, "finish_reason": "stop"}]},
]


class ExtendedFakeProviderServer(FakeProviderServer):
    def __init__(self, default_status=200, default_body=None, anthropic_body=None):
        super().__init__(default_status=default_status, default_body=default_body)
        self._anthropic_body = anthropic_body or ANTHROPIC_OK
        self._sse_queue = []
        self.messages_url = f"http://127.0.0.1:{self.port}/v1/messages"

    def set_stream(self, chunks):
        with self._lock:
            self._sse_queue = list(chunks)

    def _make_handler(self):
        server = self
        base_handler = super()._make_handler()

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _drain(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length:
                    self.rfile.read(length)

            def do_POST(self):
                self._drain()
                if self.path == "/v1/messages":
                    with server._lock:
                        body = json.dumps(server._anthropic_body).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/v1/chat/completions" and server._sse_queue:
                    with server._lock:
                        chunks = server._sse_queue
                        server._sse_queue = []
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for ch in chunks:
                        self.wfile.write(f"data: {json.dumps(ch)}\n\n".encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                base_handler(self)

        return _H


def test_extended_server_anthropic_route():
    srv = ExtendedFakeProviderServer()
    try:
        import urllib.request
        req = urllib.request.Request(
            srv.messages_url, data=b"{}", headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        assert data["stop_reason"] == "end_turn"
        assert data["content"][0]["text"] == "ok"
    finally:
        srv.shutdown()
