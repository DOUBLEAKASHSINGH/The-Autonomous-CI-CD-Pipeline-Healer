import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from models import HealerRequest, HealerResponse
from graph import run_healer_graph

app = FastAPI(
    title="CI/CD Pipeline Healer",
    description="Multi-agent LangGraph backend that diagnoses and patches failing CI builds",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "running", "service": "CI/CD Pipeline Healer"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/diagnose", response_model=HealerResponse)
async def diagnose(payload: HealerRequest):
    """
    Main endpoint called by n8n.
    Receives error log + code diff, runs the multi-agent graph,
    and returns the patched file + diagnosis summary.
    """
    if not payload.error_log.strip():
        raise HTTPException(status_code=400, detail="error_log cannot be empty")

    # Fetch the original file from GitHub if repo + file_path are provided
    original_file_content = ""
    if payload.repo and payload.file_path:
        original_file_content = await fetch_file_from_github(
            payload.repo, payload.file_path, payload.commit_sha
        )

    result = await run_healer_graph(
        error_log=payload.error_log,
        code_diff=payload.code_diff,
        original_file=original_file_content,
    )

    return HealerResponse(
        file_path=result.get("file_path", payload.file_path or "unknown"),
        patched_file=result.get("patched_file", ""),
        diagnosis=result.get("diagnosis", {}),
        verdict=result.get("verdict", "PASS"),
        reason=result.get("reason", ""),
        iterations=result.get("iterations", 1),
    )


async def fetch_file_from_github(repo: str, file_path: str, commit_sha: str = "") -> str:
    """Fetch the raw content of a file from GitHub at a specific commit."""
    token = os.getenv("GITHUB_TOKEN", "")
    ref = commit_sha if commit_sha else "main"
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{file_path}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text
        except Exception:
            return ""
