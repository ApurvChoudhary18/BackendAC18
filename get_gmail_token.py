import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()


# 👉 Replace with your CLIENT_ID and CLIENT_SECRET from Google Cloud
CLIENT_ID=os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")


def main():
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )


    creds = flow.run_local_server(port=8080, prompt="consent")
    print("✅ Access Token:", creds.token)
    print("🔄 Refresh Token:", creds.refresh_token)

if __name__ == "__main__":
    main()
