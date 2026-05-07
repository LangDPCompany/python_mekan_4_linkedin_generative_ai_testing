import requests
import os

access_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")

if not access_token:
    raise SystemExit("Set LINKEDIN_ACCESS_TOKEN in your environment.")

profile = requests.get(
    "https://api.linkedin.com/v2/userinfo",
    headers={"Authorization": f"Bearer {access_token}"}
).json()

print(profile)
print(f"\nLINKEDIN_PERSONAL_PROFILE_ID={profile['sub']}")
print(f"LINKEDIN_PERSONAL_PROFILE_URN=urn:li:person:{profile['sub']}")
