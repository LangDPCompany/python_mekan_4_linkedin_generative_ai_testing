import requests
import os

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
AUTH_CODE = os.getenv("LINKEDIN_AUTH_CODE", "")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback")

if not CLIENT_ID or not CLIENT_SECRET or not AUTH_CODE:
    raise SystemExit("Set LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, and LINKEDIN_AUTH_CODE.")

# Step 1: Exchange code for token
token_resp = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
    "grant_type": "authorization_code",
    "code": AUTH_CODE,
    "redirect_uri": REDIRECT_URI,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
})

token_data = token_resp.json()
print("TOKEN DATA:", token_data)

access_token = token_data["access_token"]

# Step 2: Get your profile (sub = your profile ID)
profile_resp = requests.get("https://api.linkedin.com/v2/userinfo", headers={
    "Authorization": f"Bearer {access_token}"
})

profile = profile_resp.json()
print("PROFILE:", profile)

# Your variables:
sub = profile["sub"]  # this is the numeric ID
print(f"\nLINKEDIN_PERSONAL_PROFILE_ID={sub}")
print(f"LINKEDIN_PERSONAL_PROFILE_URN=urn:li:person:{sub}")
