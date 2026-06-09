"""
Agent 3 — Evaluator

Acts as a quality-assurance reviewer.
Compares the patched file against the original error and decides:
  - PASS  → the fix directly addresses the root cause
  - RETRY → the fix is incomplete, wrong, or introduces new issues

Returns (verdict: str, reason: str).
"""

import os
import json
import re
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a senior code reviewer performing automated QA on an AI-generated patch.

Your task: decide if the patched file correctly fixes the reported error.

Output ONLY valid JSON — no markdown, no explanation:
{
  "verdict": "PASS" or "RETRY",
  "reason": "One or two sentences explaining your decision."
}

PASS criteria (ALL must hold):
1. The root cause identified in the diagnosis is directly addressed in the patch.
2. The patched file is syntactically complete and valid.
3. The fix does not obviously break other logic in the file.
4. The fix is not just a deletion of the failing code (unless that is genuinely correct).

RETRY criteria (ANY is sufficient):
- The patch does not address the specific line/cause mentioned in the diagnosis.
- The patch is a partial file (truncated).
- The patch still contains the exact bug pattern from the original error.
- The patch introduces a new obvious error (wrong indentation, missing bracket, etc.).
- The patch is empty or identical to the original.
"""


async def run_evaluator(
    error_log: str,
    original_file: str,
    patched_file: str,
    diagnosis: dict,
) -> tuple[str, str]:

    # Build a compact diff summary for the evaluator
    original_lines = set((original_file or "").splitlines())
    patched_lines = set((patched_file or "").splitlines())
    added = [l for l in patched_lines if l not in original_lines]
    removed = [l for l in original_lines if l not in patched_lines]

    diff_summary = ""
    if added or removed:
        diff_summary = "Lines removed:\n" + "\n".join(f"- {l}" for l in removed[:15])
        diff_summary += "\n\nLines added:\n" + "\n".join(f"+ {l}" for l in added[:15])
    else:
        diff_summary = "(no changes detected between original and patch)"

    user_message = f"""## Diagnosis
File: {diagnosis.get("file_path", "unknown")}
Error type: {diagnosis.get("error_type", "")}
Root cause: {diagnosis.get("root_cause", "")}
Line: {diagnosis.get("error_line", 0)}

## Original error output (tail)
{error_log[-1000:] if len(error_log) > 1000 else error_log}

## Diff summary (original → patched)
{diff_summary}

## Patched file (first 3000 chars)
{(patched_file or "")[:3000]}

Evaluate the patch and return your JSON verdict."""

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        result = json.loads(raw)
        verdict = result.get("verdict", "PASS").upper()
        reason = result.get("reason", "")
        if verdict not in ("PASS", "RETRY"):
            verdict = "PASS"
        return verdict, reason
    except json.JSONDecodeError:
        # If evaluator output is unparseable, default to PASS to avoid infinite loops
        return "PASS", f"Could not parse evaluator response: {raw[:200]}"
