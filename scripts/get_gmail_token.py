from urllib.parse import urlparse, parse_qs
import os, sys, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]

class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - you can close this tab")
        q = urlparse(self.path).query
        params = parse_qs(q)
        self.server.query = params
    def log_message(self, format, *args):
        return

def run_local_server(flow: InstalledAppFlow):
    port = 8080
    creds = flow.run_local_server(port=port)
    print("REFRESH_TOKEN=" + (creds.refresh_token or ""))
    print("ACCESS_TOKEN=" + (creds.token or ""))
    return creds

if __name__ == "__main__":
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print("MISSING_CLIENT_SECRET")
        sys.exit(2)
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    creds = run_local_server(flow)
    print("DONE")
