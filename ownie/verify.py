"""Cheap, deterministic checks on the model's decisions — no LLM calls.

A decision survives only if at least one of its path:line citations points
at a line the model was actually shown, and its confidence clears a floor.
This catches hallucinated locations for free.
"""

import re

MIN_CONFIDENCE = 0.5

LINE_REF = re.compile(r"([^\s:`'\"(),]+):(\d+)(?:\s*-\s*(\d+))?")


def filter_decisions(decisions, visible_lines, min_confidence=MIN_CONFIDENCE):
  """Return (kept, dropped) where dropped is a list of (decision, reason)."""
  kept, dropped = [], []

  for decision in decisions:
    if decision.confidence < min_confidence:
      dropped.append((decision, f"low confidence ({decision.confidence:.2f})"))
    elif not is_grounded(decision, visible_lines):
      dropped.append((decision, "citations don't match the code shown"))
    else:
      kept.append(decision)

  return kept, dropped


def is_grounded(decision, visible_lines):
  refs = [decision.location, *decision.evidence]
  return any(_ref_is_visible(path, start, end, visible_lines) for ref in refs for path, start, end in parse_refs(ref))


def parse_refs(text):
  for match in LINE_REF.finditer(text):
    path = match.group(1).removeprefix("./").removeprefix("b/")
    start = int(match.group(2))
    end = int(match.group(3) or start)
    yield path, start, max(start, end)


def _ref_is_visible(path, start, end, visible_lines):
  shown = visible_lines.get(path)
  return bool(shown) and any(line in shown for line in range(start, end + 1))
