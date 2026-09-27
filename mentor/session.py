"""The interactive question → answer → grade loop."""

from mentor import ui
from mentor.context import code_for
from mentor.llm import grade_answer
from mentor.record import record_result

MAX_ATTEMPTS = 3


class QuitSession(Exception):
  pass


def read_input():
  try:
    return ui.prompt().strip()
  except (EOFError, KeyboardInterrupt):
    ui.info("")
    raise QuitSession


def run_session(decisions, state, scope_label):
  """Ask about each decision in turn.

  Returns (tally, requeue): decisions to offer again via --more — the ones
  not reached because the user quit, followed by the ones they skipped.
  """
  tally = {"owned": 0, "partial": 0, "revisit": 0, "skipped": 0}
  skipped = []

  for index, decision in enumerate(decisions):
    try:
      status, answer = ask_decision(decision, index + 1, len(decisions))
    except QuitSession:
      ui.stopped()
      return tally, decisions[index:] + skipped

    record_result(state, decision, status, answer, scope_label)
    tally[status] += 1
    if status == "skipped":
      skipped.append(decision)

  return tally, skipped


def ask_decision(decision, number, total):
  ui.question_card(decision, number, total)
  ui.controls()

  code = code_for(decision)
  attempt = 0
  best = "missing"
  last_answer = None

  while True:
    text = read_input()
    command = text.lower()

    if not text:
      continue
    if command in ("q", "quit"):
      raise QuitSession
    if command in ("s", "skip"):
      return "skipped", last_answer
    if command in ("h", "hint"):
      ui.hint(decision.hint)
      continue
    if command in ("e", "explain"):
      ui.explanation(decision)
      return ("partial" if best == "partial" else "revisit"), last_answer

    attempt += 1
    last_answer = text
    with ui.working("Grading your answer…"):
      grade = grade_answer(decision, text, attempt, code=code)
    ui.verdict(grade)

    if grade.verdict == "owned":
      return "owned", text
    if grade.verdict == "partial":
      best = "partial"

    if attempt >= MAX_ATTEMPTS:
      ui.explanation(decision)
      return ("partial" if best == "partial" else "revisit"), last_answer

    ui.controls(again=True)
