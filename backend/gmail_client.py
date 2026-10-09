"""
Fetches and parses emails from Gmail.
"""

import base64
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from concurrent.futures import ThreadPoolExecutor

from gmail_auth import get_gmail_credentials


def get_gmail_service():
    creds = get_gmail_credentials()
    return build("gmail", "v1", credentials=creds)


def list_recent_messages(service, max_results=10, query=""):
    """
    Returns a list of message stubs (id, threadId) for the most recent messages.
    `query` uses Gmail search syntax, e.g. "is:unread", "newer_than:1d", "in:inbox".
    """
    results = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max_results, q=query)
        .execute()
    )
    return results.get("messages", [])


def _get_header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _extract_body(payload):
    """Recursively walks the MIME structure to find and decode the text body."""
    # Prefer plain text; fall back to stripping HTML.
    plain_text = None
    html_text = None

    def walk(part):
        nonlocal plain_text, html_text
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data")

        if body_data:
            decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            if mime_type == "text/plain" and plain_text is None:
                plain_text = decoded
            elif mime_type == "text/html" and html_text is None:
                html_text = decoded

        for sub_part in part.get("parts", []):
            walk(sub_part)

    walk(payload)

    if plain_text:
        return plain_text
    if html_text:
        return BeautifulSoup(html_text, "html.parser").get_text(separator="\n")
    return ""


def _clean_body(text, max_chars=3000):
    """Trims quoted reply chains and signatures, and caps length to control token usage."""
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Stop at common "quoted reply" markers.
        if stripped.startswith(">"):
            continue
        if stripped.startswith("On ") and " wrote:" in stripped:
            break
        if stripped.startswith("-----Original Message-----"):
            break
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned[:max_chars]


def fetch_message_details(service, message_id):
    """Fetches and parses a single email into a simple dict."""
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    headers = msg["payload"].get("headers", [])
    subject = _get_header(headers, "Subject") or "(no subject)"
    sender = _get_header(headers, "From") or "(unknown sender)"
    date = _get_header(headers, "Date") or ""

    body = _extract_body(msg["payload"])
    body = _clean_body(body)

    return {
        "id": message_id,
        "thread_id": msg.get("threadId"),
        "subject": subject,
        "sender": sender,
        "date": date,
        "snippet": msg.get("snippet", ""),
        "body": body,
    }


def fetch_recent_emails(max_results=10, query="in:inbox"):
    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    stubs = list_recent_messages(service, max_results=max_results, query=query)

    def fetch_one(stub):
        # Each thread builds its own service object, since they aren't thread-safe
        thread_service = build("gmail", "v1", credentials=creds)
        return fetch_message_details(thread_service, stub["id"])

    with ThreadPoolExecutor(max_workers=5) as pool:
        return list(pool.map(fetch_one, stubs))