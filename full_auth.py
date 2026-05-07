# full_auth.py
import requests
import webbrowser
import urllib.parse
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback")
SCOPES = "openid profile w_member_social"

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your environment.")

auth_url = (
    "https://www.linkedin.com/oauth/v2/authorization"
    f"?response_type=code"
    f"&client_id={CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
    f"&scope={urllib.parse.quote(SCOPES)}"
)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" not in params:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code found.")
            return

        code = params["code"][0]
        print(f"\n✅ Code received, exchanging for token...")

        # Exchange code for token
        token_resp = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        token_data = token_resp.json()
        print("TOKEN RESPONSE:", token_data)

        if "access_token" not in token_data:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Token exchange failed. Check terminal.")
            return

        access_token = token_data["access_token"]

        # Get profile
        profile_resp = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        profile = profile_resp.json()
        print("PROFILE:", profile)

        sub = profile.get("sub", "NOT_FOUND")

        print(f"\n{'='*50}")
        print(f"ACCESS_TOKEN={access_token}")
        print(f"LINKEDIN_PERSONAL_PROFILE_ID={sub}")
        print(f"LINKEDIN_PERSONAL_PROFILE_URN=urn:li:person:{sub}")
        print(f"{'='*50}\n")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(f"Done! Check your terminal.\nSub: {sub}".encode())

    def log_message(self, format, *args):
        pass  # suppress request logs

print("🌐 Opening browser for LinkedIn login...")
webbrowser.open(auth_url)

server = HTTPServer(("localhost", 8000), Handler)
server.handle_request()
