"""
Handles Gmail OAuth2 authentication.

Setup required before this works:
1. Go to https://console.cloud.google.com/
2. Create a project (or use an existing one)
3. Enable the "Gmail API" (APIs & Services -> Library -> search Gmail API -> Enable)
4. Go to APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
   - Application type: Desktop app
5. Download the JSON file, save it as `credentials.json` in this project folder
6. Run this script (or the main pipeline) once -- it will open a browser window
   for you to log in and grant access. A `token.json` file will be saved so you
   don't have to log in again next time.
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Read-only scope -- this agent only reads/summarizes email, never sends or deletes.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

TOKEN_PATH = "token.json"
CREDENTIALS_PATH = "credentials.json"


def get_gmail_credentials():
    """Returns valid Gmail API credentials, running the OAuth flow if needed."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"'{CREDENTIALS_PATH}' not found.\n"
                    "Download your OAuth client credentials from Google Cloud Console "
                    "and save them as 'credentials.json' in this folder.\n"
                    "See the docstring at the top of gmail_auth.py for step-by-step instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the token so we don't have to log in every time.
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


if __name__ == "__main__":
    # Running this file directly just tests that auth works.
    creds = get_gmail_credentials()
    print("✅ Authenticated successfully. token.json saved.")