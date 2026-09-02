import json
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_SOURCE_BYTES = 256 * 1024
MAX_OUTPUT_CHARS = 2000


class SastHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/scan":
            self._send(404, {"status": "error", "output": "Unknown endpoint"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_SOURCE_BYTES:
                raise ValueError("source exceeds sandbox input limit")
            payload = json.loads(self.rfile.read(length))
            source = payload.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError("source must be a non-empty string")

            with tempfile.TemporaryDirectory() as workspace:
                source_path = Path(workspace) / "generated.py"
                source_path.write_text(source, encoding="utf-8")
                result = subprocess.run(
                    ["python", "-m", "bandit", "-q", "-lll", str(source_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=workspace,
                )

            output = (result.stdout or result.stderr or "").strip()[:MAX_OUTPUT_CHARS]
            if result.returncode == 0:
                status = "clean"
            elif result.returncode == 1:
                status = "finding"
            else:
                status = "invalid" if "syntax" in output.lower() else "error"
            self._send(200, {"status": status, "output": output})
        except subprocess.TimeoutExpired:
            self._send(200, {"status": "timeout", "output": "Bandit scan timed out"})
        except (ValueError, json.JSONDecodeError, OSError) as error:
            self._send(400, {"status": "error", "output": str(error)[:MAX_OUTPUT_CHARS]})

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), SastHandler).serve_forever()
