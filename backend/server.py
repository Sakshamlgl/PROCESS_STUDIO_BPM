"""Loopback-only application server with bounded requests and structured diagnostics."""

import json
import logging
import mimetypes
import os
import sqlite3
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree.ElementTree import ParseError
import store
from service import dispatch
from validation import AppError

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("STUDIO_DB", str(ROOT / "data/studio.sqlite3")))
PORT = int(os.environ.get("STUDIO_PORT", "8765"))
LOG = logging.getLogger("process-studio")


class Handler(BaseHTTPRequestHandler):
    server_version = "ProcessStudio/2.0"
    timeout = 260

    def security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Cache-Control", "no-store" if self.path.startswith("/api/") else "no-cache"
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; worker-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )

    def respond(self, status, payload, content_type="application/json; charset=utf-8"):
        body = (
            json.dumps(payload, allow_nan=False).encode()
            if content_type.startswith("application/json")
            else payload
        )
        self.send_response(status)
        self.security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.end_headers()
        self.wfile.write(body)

    def check_host(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise AppError(
                "Only loopback Host headers are allowed", 403, "HOST_REJECTED"
            )
        if self.command == "POST":
            origin = self.headers.get("Origin")
            if origin and origin not in {
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
                "http://127.0.0.1:5173",
                "http://localhost:5173",
            }:
                raise AppError("Cross-origin write rejected", 403, "ORIGIN_REJECTED")
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise AppError("Cross-site write rejected", 403, "ORIGIN_REJECTED")

    def handle_request(self):
        self.request_id = uuid.uuid4().hex[:12]
        try:
            self.check_host()
            path = unquote(urlparse(self.path).path)
            if self.command == "GET" and not path.startswith("/api/"):
                base = (ROOT / "frontend/dist").resolve()
                file = (base / path.lstrip("/")).resolve()
                if not file.is_relative_to(base):
                    raise AppError("Forbidden path", 403, "PATH_REJECTED")
                if path == "/":
                    file = base / "index.html"
                if not file.is_file():
                    raise AppError(
                        "Asset not found; build frontend if needed", 404, "NOT_FOUND"
                    )
                content_type = (
                    {
                        ".js": "text/javascript",
                        ".css": "text/css",
                        ".svg": "image/svg+xml",
                    }.get(file.suffix)
                    or mimetypes.guess_type(str(file))[0]
                    or "application/octet-stream"
                )
                return self.respond(200, file.read_bytes(), content_type)
            data = None
            if self.command == "POST":
                if (
                    self.headers.get("Content-Type", "").split(";")[0]
                    != "application/json"
                ):
                    raise AppError("Use application/json", 415, "CONTENT_TYPE")
                if self.headers.get("Transfer-Encoding"):
                    raise AppError(
                        "Chunked uploads are not supported", 400, "INVALID_INPUT"
                    )
                length = int(self.headers.get("Content-Length", "0"))
                maximum = 10_000_000 if path == "/api/import-backup" else 2_000_000
                if not 0 < length <= maximum:
                    raise AppError(
                        f"Request must be 1–{maximum} bytes", 413, "BODY_TOO_LARGE"
                    )
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise AppError("Incomplete request body")
                data = json.loads(
                    raw,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError("Non-finite JSON numbers are forbidden")
                    ),
                )
            status, result = dispatch(DB, self.command, path, data)
            self.respond(status, result)
        except AppError as e:
            self.respond(
                e.status,
                {
                    "error": str(e),
                    "code": e.code,
                    "details": e.details,
                    "requestId": self.request_id,
                },
            )
        except (ValueError, TypeError, KeyError, ParseError, UnicodeError) as e:
            self.respond(
                400,
                {
                    "error": str(e),
                    "code": "INVALID_INPUT",
                    "requestId": self.request_id,
                },
            )
        except sqlite3.OperationalError:
            LOG.exception("database_failure request=%s", self.request_id)
            self.respond(
                503,
                {
                    "error": "Database temporarily unavailable. Retry after reloading.",
                    "code": "DATABASE_BUSY",
                    "requestId": self.request_id,
                },
            )
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            LOG.info("client_disconnected request=%s", self.request_id)
        except Exception:
            LOG.exception("request_failed request=%s", self.request_id)
            self.respond(
                500,
                {
                    "error": "Unexpected error. Check the server log with this request ID.",
                    "code": "INTERNAL_ERROR",
                    "requestId": self.request_id,
                },
            )

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def log_message(self, message, *args):
        LOG.info("http request=%s %s", getattr(self, "request_id", "-"), message % args)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32
    _slots = threading.BoundedSemaphore(16)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    store.migrate(DB)
    with LocalServer(("127.0.0.1", PORT), Handler) as server:
        LOG.info(
            "Process Family Studio 2.0: http://localhost:%s | database=%s", PORT, DB
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            LOG.info("Stopped by user")
