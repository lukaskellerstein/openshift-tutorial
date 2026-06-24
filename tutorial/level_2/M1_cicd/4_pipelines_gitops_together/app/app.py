"""Simple Python web application for the CI/CD + GitOps tutorial."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json


VERSION = os.environ.get("APP_VERSION", "1.0.0")


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "healthy", "version": VERSION})
        elif self.path == "/":
            self._respond(200, {
                "message": "Hello from the CI/CD + GitOps demo app!",
                "version": VERSION,
            })
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), DemoHandler)
    print(f"Serving on port {port}")
    server.serve_forever()
