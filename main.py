"""
Email Summarizer Agent - CLI entrypoint.

Usage:
    python main.py                     # summarize 10 most recent inbox emails, one digest
    python main.py --count 5           # summarize 5 most recent
    python main.py --individual        # print one summary per email instead of a combined digest
    python main.py --query "is:unread" # use Gmail search syntax to filter which emails to fetch
"""

import argparse

from gmail_auth import get_gmail_credentials
from summarizer import summarize_email, summarize_digest


def main():
    parser = argparse.ArgumentParser(description="Summarize recent Gmail emails using AI.")
    parser.add_argument("--count", type=int, default=10, help="Number of emails to fetch")
    parser.add_argument(
        "--query",
        type=str,
        default="in:inbox",
        help='Gmail search query (e.g. "is:unread", "newer_than:2d")',
    )
    parser.add_argument(
        "--individual",
        action="store_true",
        help="Print a separate summary per email instead of one combined digest",
    )
    args = parser.parse_args()

    print(f"Fetching {args.count} emails matching '{args.query}'...")
    emails = fetch_recent_emails(max_results=args.count, query=args.query)

    if not emails:
        print("No emails found matching that query.")
        return

    print(f"Fetched {len(emails)} emails. Summarizing...\n")

    if args.individual:
        for e in emails:
            print(f"--- {e['subject']} ({e['sender']}) ---")
            print(summarize_email(e))
            print()
    else:
        digest = summarize_digest(emails)
        print("=" * 60)
        print("EMAIL DIGEST")
        print("=" * 60)
        print(digest)


if __name__ == "__main__":
    main()