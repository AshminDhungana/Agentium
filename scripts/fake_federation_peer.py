#!/usr/bin/env python3
"""
fake_federation_peer.py — dev tool for live-verifying TODO §16.3.

Emulates a remote Agentium peer for a single local instance:
  * receives delegated tasks on POST /api/v1/federation/webhooks/tasks/receive
  * immediately posts a signed "completed" result back to the payload's
    callback_url (exercising the 16.3.3 result-callback loop end-to-end)
  * answers heartbeat probes with 200 so the peer shows as active

HMAC headers mirror backend/celery_app._signed_headers; the signing key
mirrors FederationService._derive_signing_key (SHA-256(secret + ":sign")).

Usage:
    python scripts/fake_federation_peer.py --secret my-dev-secret --port 8100

Then register this in the UI with base_url http://localhost:8100 and the
SAME shared secret.
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import httpx
except ImportError:
    sys.exit("httpx is required (already a backend dependency): pip install httpx")


def derive_signing_key(secret: str) -> str:
    """Mirror FederationService._derive_signing_key."""
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def signed_headers(peer_url: str, signing_key: str, body: bytes) -> dict:
    """Mirror backend.celery_app._signed_headers."""
    ts = int(time.time())
    sig = hmac.new(signing_key.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Agentium-Peer-Url": peer_url,
        "X-Agentium-Timestamp": str(ts),
        "X-Agentium-Signature": f"sha256={sig}",
    }


class FakePeerHandler(BaseHTTPRequestHandler):
    # Set from main(); carries --peer-url and the derived signing key.
    args: argparse.Namespace

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        if self.path.endswith("/webhooks/heartbeat"):
            print("[fake-peer] heartbeat probe received → 200 OK")
            self._reply(200, {"status": "ok"})
            return

        if self.path.endswith("/webhooks/tasks/receive"):
            payload = json.loads(raw)
            original_task_id = payload.get("original_task_id")
            callback_url = payload.get("callback_url")
            print(f"[fake-peer] received delegation {original_task_id} → {callback_url}")

            result = {
                "original_task_id": original_task_id,
                "local_task_id": f"fake-{int(time.time())}",
                "status": "completed",
                "result_summary": "Completed by fake_federation_peer (dev tool).",
                "result_data": {"source": "scripts/fake_federation_peer.py"},
            }
            body = json.dumps(result).encode()
            try:
                resp = httpx.post(
                    callback_url,
                    content=body,
                    headers=signed_headers(self.args.peer_url, self.args.signing_key, body),
                    timeout=20,
                )
                resp.raise_for_status()
                print(f"[fake-peer] result callback accepted: {resp.status_code}")
            except Exception as exc:
                print(f"[fake-peer] result callback FAILED: {exc}")

            self._reply(200, {"status": "accepted", "task_id": original_task_id})
            return

        self._reply(404, {"detail": "Not found"})

    def log_message(self, fmt, *args):  # silence http.server's stderr noise
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake Agentium federation peer (TODO 16.3 dev tool)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--secret", required=True,
                        help="Shared secret — must match the one used to register this peer in the UI")
    parser.add_argument("--peer-url", default=None,
                        help="Value sent as X-Agentium-Peer-Url — must match the registered base_url "
                             "(default: http://localhost:<port>)")
    args = parser.parse_args()

    args.signing_key = derive_signing_key(args.secret)
    if not args.peer_url:
        args.peer_url = f"http://localhost:{args.port}"
    FakePeerHandler.args = args

    server = ThreadingHTTPServer((args.host, args.port), FakePeerHandler)
    print(f"[fake-peer] listening on http://{args.host}:{args.port}")
    print(f"[fake-peer] register in the UI with base_url={args.peer_url} and the same shared secret")
    print("[fake-peer] Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
