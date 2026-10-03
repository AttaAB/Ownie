"""The non-interactive analysis: scope → context → decisions → verified.

Shared by the CLI and the eval runner, so what gets measured is exactly
what users get.
"""

from dataclasses import dataclass

from ownie import git as g
from ownie.context import build_context
from ownie.llm import extract_decisions
from ownie.record import known_decisions, mark_changed, pending_decisions
from ownie.verify import filter_decisions


@dataclass
class Analysis:
  decisions: list                 # verified, ranked, most important first
  dropped: list                   # (decision, reason) removed by verify
  found: list                     # everything the model returned, pre-verify
  context_text: str               # exactly what the model read
  truncated: bool
  context_source: str             # "diff only" / "whole files"


def analyze(scope, known=()):
  """`known`: (id, title, status) of decisions from earlier reviews, so ids are reused."""
  context = build_context(scope)
  found = extract_decisions(context.text, scope.label, known=known)
  decisions, dropped = filter_decisions(found, context.visible_lines)

  return Analysis(
    decisions=decisions,
    dropped=dropped,
    found=found,
    context_text=context.text,
    truncated=context.truncated,
    context_source="whole files" if scope.kind == "all" else "diff only",
  )


def queue_review(state, scope):
  """Find decisions in `scope` and put them at the front of the queue.

  Shared by `ownie review` and `ownie ask`. Returns (analysis, new
  decisions, titles of owned decisions whose code changed); the caller
  saves the state.
  """
  changed = mark_changed(state)
  analysis = analyze(scope, known=known_decisions(state))
  # the prompt asks for this; enforce it, since an owned decision re-asked is noise
  decisions = [d for d in analysis.decisions if state["decisions"].get(d.id, {}).get("status") != "owned"]

  # keep leftovers from earlier reviews that this one didn't return again (same id = same decision)
  new_ids = {d.id for d in decisions}
  leftovers = [d for d in pending_decisions(state) if d.id not in new_ids]
  state["pending"] = [d.model_dump() for d in decisions + leftovers]
  state["last_reviewed_commit"] = g.head_commit()
  return analysis, decisions, changed
