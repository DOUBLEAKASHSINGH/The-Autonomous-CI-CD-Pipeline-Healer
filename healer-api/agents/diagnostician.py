"""
Agent 1 — Diagnostician

Reads the raw CI error log and code diff.
Outputs a structured JSON identifying exactly what broke and where.
"""

import os
import json
import re
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a CI failure analyst. Your only job is to extract a structured diagnosis from a stack trace and code diff.

Output ONLY valid JSON — no markdown, no explanation, no code fences.

JSON schema:
{
  "file_path": "relative/path/to/file.py",
  "error_line": 42,
  "error_type": "TypeError",
  "root_cause": "One sentence: what exactly is wrong and why.",
  "language": "python"
}

Rules:
- file_path must be the file that needs to be changed to fix the error.
- error_line must be an integer (0 if unknown).
- error_type should be the exception class or compiler error name.
- root_cause must be concrete: mention the variable names and types involved.
- language: python, javascript, typescript, cpp, java, go, etc.
- If the diff shows the bug was introduced, prioritise that file.
"""


def _truncate_log(log: str, max_chars: int = 6000) -> str:
    """Keep the last N chars of the log — tail end has the most useful info."""
    if len(log) > max_chars:
        return "...[truncated]\n" + log[-max_chars:]
    return log


async def run_diagnostician(error_log: str, code_diff: str) -> dict:
    truncated_log = _truncate_log(error_log)

    user_message = f"""## Error Log
{truncated_log}

## Code Diff (what changed in the failing commit)
{code_diff[:3000] if code_diff else "(no diff provided)"}

Diagnose the failure and return the JSON."""

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if the model added them despite instructions
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: attempt to extract JSON substring
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Last resort: return a best-effort dict
        return {
            "file_path": "",
            "error_line": 0,
            "error_type": "Unknown",
            "root_cause": raw[:300],
            "language": "unknown",
        }
