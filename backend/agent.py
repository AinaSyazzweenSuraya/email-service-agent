"""
The agentic version of the email summarizer.

Key difference from the v1 pipeline:
    v1: YOU decide the Gmail query (--query "is:unread") -> code fetches -> LLM summarizes.
    v2: YOU give the LLM a *goal* ("catch me up") -> the LLM decides what to search for,
        can search multiple times with different queries, and only then produces
        a final answer.

This is done via "function calling" (also called "tool use"): we describe a tool
to the model, and instead of just returning text, the model can respond with a
function_call step ("please call search_emails(query='is:unread') for me"). Our
code executes the real function and sends the result back, and the model
continues -- possibly calling more tools -- until it's ready to answer.

IMPLEMENTATION NOTE: this uses Google's Interactions API (client.interactions),
not the older client.models.generate_content(). Gemini's newer "thinking" models
attach an encrypted thought_signature to their reasoning, and it must be passed
back unchanged on every follow-up turn or the API rejects the request. The
Interactions API handles this automatically in "stateful mode" -- you just pass
previous_interaction_id and the server manages all of that bookkeeping for you.
(The older generate_content approach requires you to manage thought signatures
by hand, which is fiddly and, as of this SDK version, has open bugs around
automatic function calling losing the signature -- see
https://github.com/googleapis/python-genai/issues for background.)
"""

import os
from google import genai
from dotenv import load_dotenv

from gmail_client import fetch_recent_emails

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY not set. Copy .env.example to .env and add your key.\n"
        "Get a free key at: https://aistudio.google.com/apikey"
    )

client = genai.Client(api_key=API_KEY)


# ---------------------------------------------------------------------------
# TOOL DEFINITION
# The Interactions API takes tool schemas as plain dicts (JSON Schema),
# rather than inferring them from a Python function's type hints. This is a
# bit more verbose to write by hand, but it's explicit about exactly what the
# model sees -- worth understanding since most non-Google LLM APIs
# (OpenAI, Claude, etc.) use this same JSON-Schema-based tool format.
# ---------------------------------------------------------------------------

SEARCH_EMAILS_TOOL = {
    "type": "function",
    "name": "search_emails",
    "description": (
        "Searches the user's Gmail inbox and returns matching emails "
        "(sender, subject, date, and body snippet for each)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "A Gmail search query. Examples: 'is:unread', 'newer_than:1d', "
                    "'is:unread newer_than:2d', 'from:someone@example.com', "
                    "'is:important', or 'in:inbox' for no filter."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of emails to return. Keep under 20.",
            },
        },
        "required": ["query"],
    },
}


def execute_search_emails(query: str, max_results: int = 10) -> str:
    """The real Python function that runs when the model calls search_emails."""
    emails = fetch_recent_emails(max_results=max_results, query=query)

    if not emails:
        return f"No emails found matching query: '{query}'"

    blocks = []
    for e in emails:
        blocks.append(
            f"From: {e['sender']}\n"
            f"Subject: {e['subject']}\n"
            f"Date: {e['date']}\n"
            f"Body: {(e['body'] or e['snippet'])[:500]}"
        )
    return "\n---\n".join(blocks)


AVAILABLE_TOOLS = {
    "search_emails": execute_search_emails,
}


# ---------------------------------------------------------------------------
# AGENT
# ---------------------------------------------------------------------------

AGENT_SYSTEM_INSTRUCTION = """You are an email assistant agent. The user will give you \
a goal (e.g. "catch me up on anything urgent" or "summarize today's inbox").

You have a `search_emails` tool that queries the user's real Gmail inbox using Gmail \
search syntax. Decide what queries to run yourself based on the user's goal -- you may \
call the tool more than once with different queries if that helps (e.g. checking unread \
mail AND checking for anything marked important).

Once you have enough information, give the user a concise, well-organized final answer. \
Group related emails, flag anything needing action, and keep it scannable -- this is \
being read on a phone, not studied like a report."""

MAX_TOOL_CALL_ROUNDS = 5  # safety cap so a confused model can't loop forever


def run_agent(user_goal: str, verbose: bool = True, on_tool_call=None) -> str:
    """
    Runs the agent loop using the Interactions API:
      1. Send the goal + tool definition, in "stateful" mode (store=True, the
         default) so Google's servers track conversation state -- including
         thought signatures -- for us.
      2. If the model responds with function_call step(s), execute them for
         real and send the result(s) back using previous_interaction_id to
         continue the same conversation.
      3. Repeat until the model responds with plain text instead of a function
         call, or we hit the safety cap.
    """
    interaction = client.interactions.create(
        model=MODEL_NAME,
        input=user_goal,
        system_instruction=AGENT_SYSTEM_INSTRUCTION,
        tools=[SEARCH_EMAILS_TOOL],
    )

    for round_num in range(1, MAX_TOOL_CALL_ROUNDS + 1):
        steps = interaction.steps or []
        function_calls = [step for step in steps if step.type == "function_call"]

        if not function_calls:
            # Model gave a final text answer -- we're done. `output_text` is a
            # convenience field the SDK computes for us from the model_output
            # step(s), so we don't need to dig through step.content ourselves.
            return interaction.output_text

        # Execute every requested tool call for real, and build the
        # function_result inputs to send back.
        function_results = []
        for call in function_calls:
            tool_fn = AVAILABLE_TOOLS.get(call.name)

            if verbose:
                print(f"  [round {round_num}] agent is calling {call.name}({dict(call.arguments)})")
            if on_tool_call:
                on_tool_call(call.name, dict(call.arguments))

            if tool_fn is None:
                result_text = f"Error: unknown tool '{call.name}'"
            else:
                try:
                    result_text = tool_fn(**call.arguments)
                except Exception as e:
                    result_text = f"Error running {call.name}: {e}"

            function_results.append({
                "type": "function_result",
                "call_id": call.id,
                "name": call.name,
                "result": result_text,
            })

        # Continue the SAME conversation -- previous_interaction_id tells the
        # server to load prior state (including thought signatures) for us.
        interaction = client.interactions.create(
            model=MODEL_NAME,
            previous_interaction_id=interaction.id,
            input=function_results,
            tools=[SEARCH_EMAILS_TOOL],
        )

    return (
        "Agent stopped after too many tool-call rounds without a final answer. "
        "Try a more specific goal."
    )