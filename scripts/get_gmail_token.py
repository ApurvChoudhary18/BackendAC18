import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

# Load .env from backend/.env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

# Gmail ke liye scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": os.getenv("CLIENT_ID"),
                "client_secret": os.getenv("CLIENT_SECRET"),
                "redirect_uris": [os.getenv("REDIRECT_URI")],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        SCOPES,
    )

    # ⚠️ Port ko 8080 kar le (ya koi aur free port jo tu ne Google Console me add kiya hai)
    creds = flow.run_local_server(port=8080, prompt='consent')
    print("✅ Access Token:", creds.token)
    print("🔄 Refresh Token:", creds.refresh_token)

if __name__ == "__main__":
    main()
