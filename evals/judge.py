"""LLM-as-judge: match predicted decisions to labels and score question quality.

The judge sees the same code Ownie saw. Its model can be set
separately with OWNIE_JUDGE_MODEL so Ownie isn't grading itself
with an identical setup.
"""

import os

from pydantic import BaseModel, Field

from ownie.llm import parse


def judge_model():
  return os.environ.get("OWNIE_JUDGE_MODEL") or os.environ.get("MENTOR_JUDGE_MODEL") or None  # None → same as Ownie


class Match(BaseModel):
  predicted_id: str
  label_id: str | None = Field(description="id of the matching labelled decision, or null if none")
  is_real_decision: bool = Field(
    description="for unmatched predictions: is this nonetheless a real, "
                "consequential design decision supported by the code? "
                "true for matched predictions"
  )
  reason: str = Field(description="one sentence")


class MatchSet(BaseModel):
  matches: list[Match]


class QualityScore(BaseModel):
  predicted_id: str
  grounded: int = Field(description="1-5: claims follow from code actually shown")
  important: int = Field(description="1-5: understanding this matters in review/incident/handoff")
  non_leaking: int = Field(description="1-5: setup and question do not reveal the consequence or fix")
  specific: int = Field(description="1-5: concrete scenario tied to this code, not generic advice")
  answerable: int = Field(description="1-5: a developer could answer in a few sentences from the code")
  central: int | None = Field(description="1-5: targets the decision's most important consequence, not an edge case or contrived setup")
  note: str = Field(description="one sentence on the biggest weakness, or 'none'")


class QualitySet(BaseModel):
  scores: list[QualityScore]


MATCH_PROMPT = """\
You are evaluating a tool that finds implicit design decisions in code.
Match each PREDICTED decision to at most one LABELLED decision (the ground
truth). A match means they are about the same underlying decision and
consequence, even if worded differently or cited at slightly different
lines. A prediction that only touches the same code but is about a
different consequence is NOT a match.

For predictions with no match, judge whether it is still a real,
consequential design decision supported by the code (not style, not
trivia, not hallucinated).

Return exactly one entry per predicted decision.

LABELLED decisions:
{labels}

PREDICTED decisions:
{predicted}

Code the tool was shown:
{code}
"""

QUALITY_PROMPT = """\
You are evaluating Socratic questions a tool asks a developer about design
decisions in their own (possibly AI-written) code. The goal of each
question is to make the developer derive the consequence themselves.

Score each question 1-5 on each criterion (5 = excellent):
- grounded: the setup/question's claims follow from the code shown
- important: understanding this matters in code review, incidents, handoffs
- non_leaking: neither the setup nor the question gives away the consequence
  or the fix (a question that says "given the race condition..." leaks)
- specific: a concrete scenario tied to this code, not generic advice
- answerable: a developer could answer in a few sentences by reading the code
- central: the scenario targets the decision's most important consequence
  (what a reviewer would expect the developer to know), not a niche edge
  case or a contrived setup that only an expert in this exact code would
  think of

Be strict: 3 is acceptable, 5 is rare.

Questions:
{questions}

Code:
{code}
"""


def match_decisions(labels, predicted, code):
  if not predicted:
    return []
  label_text = "\n".join(f"- id={l.id} | {l.title} | {l.location} | {l.key_point.strip()}" for l in labels)
  predicted_text = "\n".join(
    f"- id={d.id} | {d.title} | {d.location} | consequences: {'; '.join(d.consequences)}" for d in predicted
  )
  result = parse(MATCH_PROMPT.format(labels=label_text, predicted=predicted_text, code=code), MatchSet, model=judge_model())

  valid_labels = {l.id for l in labels}
  by_id = {m.predicted_id: m for m in result.matches}
  matches = []
  for d in predicted:
    m = by_id.get(d.id) or Match(predicted_id=d.id, label_id=None, is_real_decision=False, reason="judge omitted it")
    if m.label_id not in valid_labels:
      m.label_id = None
    if m.label_id:
      m.is_real_decision = True
    matches.append(m)
  return matches


def score_questions(predicted, code):
  if not predicted:
    return []
  questions = "\n\n".join(
    f"id={d.id}\nlocation: {d.location}\nsetup: {d.setup}\nquestion: {d.question}" for d in predicted
  )
  result = parse(QUALITY_PROMPT.format(questions=questions, code=code), QualitySet, model=judge_model())

  by_id = {s.predicted_id: s for s in result.scores}
  return [by_id[d.id] for d in predicted if d.id in by_id]
