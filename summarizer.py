"""
Sends emails to Gemini for summarization.
"""

import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

if not API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY not set. Copy .env.example to .env and add your key.\n"
        "Get a free key at: https://aistudio.google.com/apikey"
    )

genai.configure(api_key=API_KEY)
_model = genai.GenerativeModel(MODEL_NAME)


SINGLE_EMAIL_PROMPT = """You are summarizing an email for someone who wants to quickly \
understand what it's about without reading the whole thing.

Give a summary in this format:
- One line: what it's about
- Any action needed (or "No action needed")

Keep it under 40 words total. Be direct, no fluff.

Email details:
From: {sender}
Subject: {subject}
Body:
{body}
"""

DIGEST_PROMPT = """You are creating a short daily email digest for someone. \
Below are their recent emails. Group and summarize them so they can scan it in a few seconds.

For each email, give:
- Sender/subject (short)
- One-line summary
- Flag if action is needed

At the end, list which emails (if any) seem to need a reply or action, ordered by likely importance.

Emails:
{emails_block}
"""


def summarize_email(email: dict) -> str:
    """Summarizes a single email dict (from gmail_client.fetch_message_details)."""
    prompt = SINGLE_EMAIL_PROMPT.format(
        sender=email["sender"],
        subject=email["subject"],
        body=email["body"] or email["snippet"],
    )
    response = _model.generate_content(prompt)
    return response.text.strip()


def summarize_digest(emails: list[dict]) -> str:
    """Summarizes a batch of emails into one combined digest."""
    blocks = []
    for i, e in enumerate(emails, 1):
        blocks.append(
            f"[{i}] From: {e['sender']}\nSubject: {e['subject']}\n"
            f"Body: {e['body'] or e['snippet']}\n"
        )
    emails_block = "\n---\n".join(blocks)

    prompt = DIGEST_PROMPT.format(emails_block=emails_block)
    response = _model.generate_content(prompt)
    return response.text.strip()