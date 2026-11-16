#!/usr/bin/env python3
"""Local-only discovery, WebSocket and HTTP request recorder for acceptance tests."""
import base64
import hashlib
import json
import os
import ssl
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


EVENTS = []
LOCK = threading.Lock()


def record(kind, value):
    with LOCK:
        EVENTS.append({"time": time.time(), "kind": kind, "value": value})


def read_exact(stream, size):
    result = b""
    while len(result) < size:
        part = stream.read(size - len(result))
        if not part:
            raise EOFError
        result += part
    return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def respond(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Upgrade", "").lower() == "websocket":
            return self.websocket()
        if self.path == "/events":
            with LOCK:
                events = list(EVENTS)
            return self.respond(events)
        if self.path.startswith("/api/v3/servicediscovery"):
            host = os.environ.get("FIXTURE_HOST", "namespace-filter-fixture:8443")
            return self.respond({"version": "v3", "response": {
                "api-server": "https://" + host,
                "event-receiver-http": "https://" + host,
                "metrics": "https://" + host,
                "synchronizer": "wss://" + host + "/sync",
            }})
        # Component health endpoints and harmless discovery adjunct requests.
        self.respond({})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw.decode(errors="replace")
        # Headers are deliberately not retained (they can contain credentials).
        record("http", {"path": self.path,
                        "body": body if self.path.split("?", 1)[0] == "/v1/scanImage" else "[body omitted]"})
        self.respond({})

    def websocket(self):
        key = self.headers["Sec-WebSocket-Key"]
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        record("websocket-connected", {})
        fragments = bytearray()
        try:
            while True:
                first, second = read_exact(self.rfile, 2)
                size = second & 127
                if size == 126:
                    size = struct.unpack("!H", read_exact(self.rfile, 2))[0]
                elif size == 127:
                    size = struct.unpack("!Q", read_exact(self.rfile, 8))[0]
                if size > 16 * 1024 * 1024:
                    raise ValueError("unexpectedly large frame")
                mask = read_exact(self.rfile, 4) if second & 128 else b""
                payload = read_exact(self.rfile, size)
                if mask:
                    payload = bytes(v ^ mask[i % 4] for i, v in enumerate(payload))
                opcode = first & 15
                if opcode == 8:
                    break
                if opcode == 9:
                    self.wfile.write(bytes([138, len(payload)]) + payload)
                    self.wfile.flush()
                    continue
                if opcode in (0, 1, 2):
                    fragments.extend(payload)
                    if first & 128:
                        try:
                            message = json.loads(fragments)
                            # Namespace routing is carried in the protocol envelope.
                            # Avoid retaining arbitrary cluster object/Secret contents.
                            record("sync", {key: value for key, value in message.items()
                                            if key not in ("Object", "Patch", "BaseObject")})
                        except ValueError:
                            record("sync-invalid", fragments.decode(errors="replace"))
                        fragments.clear()
        except (EOFError, OSError, ValueError):
            pass
        self.close_connection = True


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/tls/tls.crt", "/tls/tls.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    # Plain HTTP is an Operator dispatch recorder; discovery/WebSocket use TLS.
    threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever,
                     daemon=True).start()
    server.serve_forever()
