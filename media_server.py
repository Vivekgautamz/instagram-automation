import http.server
import socketserver
import os
import sys

PORT = 8000
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reels", "new")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def start_server():
    os.makedirs(DIRECTORY, exist_ok=True)
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print("=" * 55)
        print("      LOCAL REELS MEDIA SERVER RUNNING")
        print("=" * 55)
        print(f"Serving files from: {DIRECTORY}")
        print(f"Local URL: http://localhost:{PORT}/<video_file.mp4>")
        print("-" * 55)
        print("[TIP] To make this accessible to Meta's servers, run Cloudflare Tunnel:")
        print(f"      cloudflared tunnel --url http://localhost:{PORT}")
        print("=" * 55)
        print("\nPress Ctrl+C to stop the server.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == "__main__":
    start_server()
