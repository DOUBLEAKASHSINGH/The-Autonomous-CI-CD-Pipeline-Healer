"""
Agent 2 — Coder

Receives the structured diagnosis + original file content.
Returns the FULL corrected file as plain text.
No explanation, no markdown — just the fixed code.
"""

import os
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a code repair bot. You receive a broken file and a precise diagnosis of what is wrong.

Return ONLY the corrected, complete file content — nothing else.
- No markdown code fences (no ``` or ```python)
- No explanations before or after the code
- No comments saying "fixed here" unless a comment was already in the original
- The file must be syntactically valid and complete
- Do NOT truncate the file — return every line

Language-specific rules:
- C++: prefer `using namespace std;` over std:: prefixes where appropriate
- Python: preserve all existing imports, class structure, and indentation style
- JavaScript/TypeScript: preserve existing module format (ESM vs CJS)
"""


def _build_user_message(diagnosis: dict, original_file: str, error_log: str) -> str:
    file_path = diagnosis.get("file_path", "unknown file")
    error_type = diagnosis.get("error_type", "Unknown error")
    root_cause = diagnosis.get("root_cause", "")
    error_line = diagnosis.get("error_line", 0)
    language = diagnosis.get("language", "")

    parts = [
        f"## File to fix: `{file_path}`",
        f"## Error type: {error_type}",
        f"## Line: {error_line}",
        f"## Root cause: {root_cause}",
    ]

    if language:
        parts.append(f"## Language: {language}")

    if original_file:
        parts.append(f"\n## Original file content:\n{original_file}")
    else:
        parts.append(
            "\n## Note: original file content not available. "
            "Reconstruct a minimal correct version based on the error context."
        )

    # Include a short excerpt of the error for coder context
    log_tail = error_log[-1500:] if len(error_log) > 1500 else error_log
    parts.append(f"\n## Relevant error output:\n{log_tail}")

    parts.append("\nReturn the complete corrected file now:")

    return "\n".join(parts)


async def run_coder(diagnosis: dict, original_file: str, error_log: str) -> str:
    user_message = _build_user_message(diagnosis, original_file, error_log)

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    patched = response.content[0].text.strip()

    # Strip markdown fences if present
    if patched.startswith("```"):
        lines = patched.split("\n")
        # Remove first line (```python etc) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        patched = "\n".join(lines)

    return patched
