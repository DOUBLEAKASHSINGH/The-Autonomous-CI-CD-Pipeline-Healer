"""
LangGraph multi-agent graph for CI/CD Pipeline Healer.

Graph flow:
  START → diagnostician → coder → evaluator → END
                              ↑________|  (on RETRY, up to MAX_ITERATIONS)
"""

import asyncio
from typing import TypedDict, Optional, Annotated
from langgraph.graph import StateGraph, END
from agents.diagnostician import run_diagnostician
from agents.coder import run_coder
from agents.evaluator import run_evaluator

MAX_ITERATIONS = 3


class HealerState(TypedDict):
    # Inputs
    error_log: str
    code_diff: str
    original_file: str

    # Agent outputs (populated as graph runs)
    file_path: Optional[str]
    diagnosis: Optional[dict]
    patched_file: Optional[str]
    verdict: Optional[str]
    reason: Optional[str]

    # Control
    iterations: int


# ── Node functions ─────────────────────────────────────────────────────────────

async def diagnostician_node(state: HealerState) -> dict:
    """Agent 1: Extract the structured diagnosis from the raw error log."""
    diagnosis = await run_diagnostician(
        error_log=state["error_log"],
        code_diff=state["code_diff"],
    )
    return {
        "diagnosis": diagnosis,
        "file_path": diagnosis.get("file_path", ""),
    }


async def coder_node(state: HealerState) -> dict:
    """Agent 2: Write the patch based on the diagnosis."""
    patched = await run_coder(
        diagnosis=state["diagnosis"],
        original_file=state["original_file"],
        error_log=state["error_log"],
    )
    return {
        "patched_file": patched,
        "iterations": state.get("iterations", 0) + 1,
    }


async def evaluator_node(state: HealerState) -> dict:
    """Agent 3: Validate the patch. Returns PASS or RETRY."""
    verdict, reason = await run_evaluator(
        error_log=state["error_log"],
        original_file=state["original_file"],
        patched_file=state["patched_file"],
        diagnosis=state["diagnosis"],
    )
    return {
        "verdict": verdict,
        "reason": reason,
    }


# ── Conditional routing ────────────────────────────────────────────────────────

def route_after_evaluator(state: HealerState) -> str:
    """
    If evaluator says PASS (or we've hit max retries), finish.
    Otherwise loop back to the coder.
    """
    verdict = state.get("verdict", "PASS")
    iterations = state.get("iterations", 0)

    if verdict == "PASS" or iterations >= MAX_ITERATIONS:
        return "done"
    return "retry"


# ── Build the graph ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    workflow = StateGraph(HealerState)

    workflow.add_node("diagnostician", diagnostician_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("evaluator", evaluator_node)

    workflow.set_entry_point("diagnostician")
    workflow.add_edge("diagnostician", "coder")
    workflow.add_edge("coder", "evaluator")

    workflow.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "done": END,
            "retry": "coder",   # cycle back
        },
    )

    return workflow.compile()


# Singleton compiled graph (built once on startup)
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_healer_graph(
    error_log: str,
    code_diff: str,
    original_file: str,
) -> dict:
    """Entry point called by main.py. Returns the final state dict."""
    graph = get_graph()

    initial_state: HealerState = {
        "error_log": error_log,
        "code_diff": code_diff,
        "original_file": original_file,
        "file_path": None,
        "diagnosis": None,
        "patched_file": None,
        "verdict": None,
        "reason": None,
        "iterations": 0,
    }

    final_state = await graph.ainvoke(initial_state)
    return final_state
