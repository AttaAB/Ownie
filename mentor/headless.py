"""Non-interactive commands for driving a review from a tool (e.g. Claude Code).

  mentor ask [scope flags | --more | --revisit] [-n N]   next questions
  mentor answer ID "TEXT"   (or TEXT on stdin)          grade an answer
  mentor hint ID  ·  mentor explain ID  ·  mentor skip ID

Each prints one JSON object. They share the pipeline and `.mentor/` state
with `mentor review`, so the record and ownership score stay in step.
Answers not yet finished are tracked in state["in_progress"] (attempts and
best verdict), so a question behaves the same as in the terminal loop.
"""

import json
from pathlib import Path

from mentor.context import code_for
from mentor.llm import grade_answer
from mentor.pipeline import queue_review
from mentor.record import (LOCATION, load_state, ownership, pending_decisions, record_result, revisit_decisions,
                           save_state)
from mentor.scope import resolve_scope
from mentor.session import MAX_ATTEMPTS

SCOPE_LABEL = "claude code"
MAX_CODE_LINES = 30


def ask(args):
  state = load_state()
  if args.more:
    decisions, label = pending_decisions(state), "decisions not asked yet"
  elif args.revisit:
    decisions, label = revisit_decisions(state), "decisions not owned yet"
  else:
    # first run in a repo: no one to ask, so review the whole project
    scope = resolve_scope(args, state, lambda prompt, options: "whole")
    if scope.is_empty:
      return _print({"scope": scope.label, "questions": [], "not_shown": 0,
                     "message": f"Nothing to review ({scope.label}). Try `--more`, `--revisit`, or `--all`."})
    _, new, changed = queue_review(state, scope)
    save_state(state)
    decisions, label = new, scope.label
    if changed:
      label += f" (plus {len(changed)} owned decision(s) whose code changed)"

  asked = decisions[:args.n]
  _print({
    "scope": label,
    "questions": [_question(d, i) for i, d in enumerate(asked, 1)],
    "not_shown": len(decisions) - len(asked),
    "message": None if asked else "No design decisions to ask about. Try `--more`, `--revisit`, or `--all`.",
  })


def answer(decision_id, text):
  state = load_state()
  decision = _find(state, decision_id)
  progress = state.setdefault("in_progress", {}).setdefault(decision_id, {"attempts": 0, "best": "missing"})
  progress["attempts"] += 1

  grade = grade_answer(decision, text, progress["attempts"], code=code_for(decision))
  if grade.verdict == "partial":
    progress["best"] = "partial"

  result = {"id": decision_id, "verdict": grade.verdict, "feedback": grade.feedback,
            "attempt": progress["attempts"], "attempts_left": MAX_ATTEMPTS - progress["attempts"]}
  if grade.verdict == "owned":
    _finish(state, decision, "owned", text)
    result["done"] = True
  elif progress["attempts"] >= MAX_ATTEMPTS:
    _finish(state, decision, progress["best"] if progress["best"] == "partial" else "revisit", text)
    result.update(done=True, explanation=_explanation(decision))
  else:
    result["done"] = False
  save_state(state)
  result["ownership"] = _ownership(state)
  _print(result)


def hint(decision_id):
  decision = _find(load_state(), decision_id)
  _print({"id": decision_id, "hint": decision.hint})


def explain(decision_id):
  state = load_state()
  decision = _find(state, decision_id)
  progress = state.get("in_progress", {}).get(decision_id, {})
  status = "partial" if progress.get("best") == "partial" else "revisit"
  _finish(state, decision, status, None)
  save_state(state)
  _print({"id": decision_id, "status": status, "explanation": _explanation(decision), "ownership": _ownership(state)})


def skip(decision_id):
  state = load_state()
  decision = _find(state, decision_id)
  rest = [d for d in state["pending"] if d["id"] != decision_id]
  if len(rest) < len(state["pending"]):
    state["pending"] = rest + [decision.model_dump()]  # to the back of the --more queue
  save_state(state)
  _print({"id": decision_id, "skipped": True})


def _find(state, decision_id):
  for d in pending_decisions(state) + revisit_decisions(state):
    if d.id == decision_id:
      return d
  _print({"error": f"no open decision with id {decision_id!r}; run `mentor ask` for current ids"})
  raise SystemExit(1)


def _finish(state, decision, status, text):
  record_result(state, decision, status, text, SCOPE_LABEL)
  state["pending"] = [d for d in state["pending"] if d["id"] != decision.id]
  state.get("in_progress", {}).pop(decision.id, None)


def _question(decision, number):
  return {
    "number": number,
    "id": decision.id,
    "category": decision.category,
    "location": decision.location,
    "setup": decision.setup,
    "question": decision.question,
    "code": _code(decision.location),
  }


def _code(location):
  """The cited lines, numbered, as plain text (None if unreadable)."""
  match = LOCATION.match(location)
  if not match:
    return None
  path, start, end = match[1], int(match[2]), int(match[3] or match[2])
  try:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
  except (OSError, UnicodeDecodeError):
    return None
  end = min(end, len(lines), start + MAX_CODE_LINES - 1)
  return "\n".join(f"{n:>4}  {lines[n - 1]}" for n in range(start, end + 1))


def _explanation(decision):
  return {
    "chosen": decision.chosen,
    "alternatives": decision.alternatives,
    "consequences": decision.consequences,
    "reference_answer": decision.reference_answer,
  }


def _ownership(state):
  owned, total = ownership(state)
  return {"owned": owned, "total": total}


def _print(data):
  print(json.dumps(data, indent=2, ensure_ascii=False))
