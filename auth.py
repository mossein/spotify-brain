import socket
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from utils import load_config, BASE_DIR

SCOPES = "user-library-read user-top-read user-read-recently-played"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
CACHE_PATH = str(BASE_DIR / ".cache-spotipy")


class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    error = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Done! You can close this tab.</h2></body></html>")
        elif "error" in params:
            _CallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Error: {_CallbackHandler.error}</h2></body></html>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress server logs


def _port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def get_spotify_client():
    config = load_config()
    if not config:
        raise SystemExit("No config found. Run: python3 brain.py setup")

    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
    if not client_id or not client_secret:
        raise SystemExit("Missing client_id or client_secret in config. Run: python3 brain.py setup")

    sp_oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        cache_path=CACHE_PATH,
    )

    # Check for cached token first
    token_info = sp_oauth.get_cached_token()
    if token_info:
        return spotipy.Spotify(auth=token_info["access_token"])

    # Need to authenticate - try local server first
    auth_url = sp_oauth.get_authorize_url()

    if _port_available(8888):
        _CallbackHandler.auth_code = None
        _CallbackHandler.error = None
        server = HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        print("  Opening browser for Spotify authorization...")
        webbrowser.open(auth_url)

        # Wait for callback (timeout after 120s)
        import time
        deadline = time.time() + 120
        while _CallbackHandler.auth_code is None and _CallbackHandler.error is None:
            if time.time() > deadline:
                server.shutdown()
                raise SystemExit("Authorization timed out after 120 seconds.")
            time.sleep(0.1)

        server.shutdown()

        if _CallbackHandler.error:
            raise SystemExit(f"Authorization failed: {_CallbackHandler.error}")

        token_info = sp_oauth.get_access_token(_CallbackHandler.auth_code)
    else:
        # Fallback: manual paste
        print(f"  Open this URL in your browser:\n  {auth_url}\n")
        redirect_url = input("  Paste the redirect URL here: ").strip()
        code = sp_oauth.parse_response_code(redirect_url)
        token_info = sp_oauth.get_access_token(code)

    return spotipy.Spotify(auth=token_info["access_token"])
