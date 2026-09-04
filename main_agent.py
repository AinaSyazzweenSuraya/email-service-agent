"""
Email Agent (v2) - CLI entrypoint.

Unlike v1's main.py, you don't specify a Gmail query yourself -- you give the
agent a *goal* in plain English, and it decides what to search for.

Usage:
    python main_agent.py "catch me up on anything urgent"
    python main_agent.py "summarize today's inbox"
    python main_agent.py "did I get any emails I need to reply to?"

If no goal is given, a default one is used.
"""

import sys
from backend.agent import run_agent

DEFAULT_GOAL = "Summarize what's new in my inbox and flag anything that needs a reply."


def main():
    goal = " ".join(sys.argv[1:]).strip() or DEFAULT_GOAL

    print(f"Goal: {goal}\n")
    print("Agent is thinking (this may call your inbox one or more times)...\n")

    result = run_agent(goal)

    print("=" * 60)
    print("AGENT RESPONSE")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()