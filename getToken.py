import requests
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import os

# ===== CONFIG =====
CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your environment.")

SCOPES = "openid profile w_member_social"

auth_url = (
    "https://www.linkedin.com/oauth/v2/authorization"
    f"?response_type=code"
    f"&client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&scope={SCOPES.replace(' ', '%20')}"
)

# ===== SERVER TO CATCH CODE =====
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            code = params["code"][0]

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Token alindi, console-a bax!")

            print("\n✅ CODE ALINDI:", code)

            # ===== EXCHANGE FOR TOKEN =====
            token_url = "https://www.linkedin.com/oauth/v2/accessToken"

            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }

            response = requests.post(token_url, data=data)
            print("\n🎯 TOKEN RESPONSE:")
            print(response.json())

        else:
            self.send_response(400)
            self.end_headers()

# ===== RUN =====
print("🌐 Brauzer açılır...")
webbrowser.open(auth_url)

server = HTTPServer(("localhost", 8000), Handler)
server.handle_request()
