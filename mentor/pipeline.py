"""The non-interactive analysis: scope → context → decisions → verified.

Shared by the CLI and the eval runner, so what gets measured is exactly
what users get.
"""

from dataclasses import dataclass

from mentor.context import build_context
from mentor.llm import extract_decisions
from mentor.verify import filter_decisions


@dataclass
class Analysis:
  decisions: list                 # verified, ranked, most important first
  dropped: list                   # (decision, reason) removed by verify
  found: list                     # everything the model returned, pre-verify
  context_text: str               # exactly what the model read
  truncated: bool
  context_source: str             # "diff only" / "whole files"


def analyze(scope, owned_titles=()):
  context = build_context(scope)
  found = extract_decisions(context.text, scope.label, owned_titles=owned_titles)
  decisions, dropped = filter_decisions(found, context.visible_lines)

  return Analysis(
    decisions=decisions,
    dropped=dropped,
    found=found,
    context_text=context.text,
    truncated=context.truncated,
    context_source="whole files" if scope.kind == "all" else "diff only",
  )
