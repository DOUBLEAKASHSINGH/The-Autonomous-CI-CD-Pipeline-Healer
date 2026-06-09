from pydantic import BaseModel
from typing import Optional


class HealerRequest(BaseModel):
    """Payload sent from n8n to the /diagnose endpoint."""
    error_log: str                        # Raw CI failure log (stack trace)
    code_diff: str = ""                   # Unified diff of the failing commit
    repo: Optional[str] = None            # e.g. "DOUBLEAKASHSINGH/my-repo"
    commit_sha: Optional[str] = None      # SHA of the failing commit
    file_path: Optional[str] = None       # If already known, pass the file to fix

    class Config:
        json_schema_extra = {
            "example": {
                "error_log": "TypeError: unsupported operand type(s) for +: 'int' and 'str'\n  File 'app/utils.py', line 42, in calculate_total",
                "code_diff": "--- a/app/utils.py\n+++ b/app/utils.py\n@@ -40,7 +40,7 @@\n-    return count + items\n+    return count + str(items)",
                "repo": "DOUBLEAKASHSINGH/The-Autonomous-CI-CD-Pipeline-Healer",
                "commit_sha": "abc123def456",
                "file_path": "app/utils.py",
            }
        }


class DiagnosisResult(BaseModel):
    file_path: str = ""
    error_line: int = 0
    error_type: str = ""
    root_cause: str = ""


class HealerResponse(BaseModel):
    """Response sent back to n8n after the agent graph completes."""
    file_path: str                        # Path of the fixed file
    patched_file: str                     # Full content of the corrected file
    diagnosis: dict                       # Structured diagnosis from Agent 1
    verdict: str                          # "PASS" or "RETRY" (final state)
    reason: str                           # Evaluator's reasoning
    iterations: int                       # How many coder attempts were made
