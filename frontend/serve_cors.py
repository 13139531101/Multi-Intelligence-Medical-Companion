"""Simple CORS-enabled HTTP server for testing"""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import sys

class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def log_message(self, format, *args):
        pass  # 静默

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = HTTPServer(("0.0.0.0", port), CORSHandler)
    print(f"[CORS server] running on http://localhost:{port}")
    print(f"   test page: http://localhost:{port}/test_page.html")
    server.serve_forever()