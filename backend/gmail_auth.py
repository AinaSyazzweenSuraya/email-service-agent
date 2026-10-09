"""
Handles Gmail OAuth2 authentication.
Works locally (files) and on Vercel (settings -> files in /tmp).
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# On Vercel only the /tmp folder can be written to.
ON_VERCEL = bool(os.getenv("VERCEL"))
BASE_DIR = "/tmp" if ON_VERCEL else "."

TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")


def _write_from_env(env_name: str, path: str):
    """If a Vercel setting holds the file contents, write it out as a file."""
    value = os.getenv(env_name)
    if value and not os.path.exists(path):
        with open(path, "w") as f:
            f.write(value)


_write_from_env("GOOGLE_CREDENTIALS_JSON", CREDENTIALS_PATH)
_write_from_env("GOOGLE_TOKEN_JSON", TOKEN_PATH)


def get_gmail_credentials():
    """Returns valid Gmail API credentials, running the OAuth flow if needed."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if ON_VERCEL:
                raise RuntimeError(
                    "Gmail login expired. Log in again on your computer and "
                    "update the GOOGLE_TOKEN_JSON setting in Vercel."
                )
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"'{CREDENTIALS_PATH}' not found. See the setup steps in "
                    "Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


if __name__ == "__main__":
    creds = get_gmail_credentials()
    print("Authenticated successfully. token.json saved.")