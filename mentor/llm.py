import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from mentor.models import DecisionSet, Grade

USER_ENV_FILE = Path.home() / ".config" / "mentor" / ".env"
DEV_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Key lookup order: real environment (never overridden) → user config →
# this project's own .env (development). The reviewed repo's .env is
# deliberately not read: it belongs to the user's app, not to mentor.
load_dotenv(USER_ENV_FILE)
load_dotenv(DEV_ENV_FILE)

DEFAULT_MODEL = "gpt-5.6-luna"
REQUEST_TIMEOUT_SECONDS = 300
MAX_DECISIONS = 12


class MissingAPIKey(Exception):
  pass


def ensure_api_key():
  if not os.environ.get("OPENAI_API_KEY"):
    raise MissingAPIKey(
      "No OpenAI API key found. Set one with either:\n"
      "  export OPENAI_API_KEY=sk-...\n"
      f"  or put OPENAI_API_KEY=sk-... in {USER_ENV_FILE}"
    )

_client = None


def _get_client():
  global _client
  if _client is None:
    # A stuck request once stalled an eval run for 40+ minutes; fail fast and retry.
    _client = OpenAI(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=2)
  return _client


def model_name():
  return os.environ.get("MENTOR_MODEL", DEFAULT_MODEL)


def parse(prompt, schema, model=None):
  """One structured-output call: returns an instance of `schema`."""
  response = _get_client().responses.parse(model=model or model_name(), input=prompt, text_format=schema)
  return response.output_parsed


EXTRACT_PROMPT = """\
You help developers take ownership of code they did not write themselves —
typically code produced by an AI coding assistant. Such code is full of
design decisions the developer never consciously made: a storage choice, a
concurrency assumption, an error-handling policy, a library, a data shape,
an API contract. The developer will be asked to explain these decisions in
code reviews, incidents, and handoffs.

Your job:
1. Take an inventory of the design decisions embedded in the code below.
   Go through it file by file so nothing load-bearing is skipped.
2. For each, build an answer key FIRST — what was chosen, realistic
   alternatives, concrete consequences, and path:line evidence — then write
   a question that makes the developer derive those consequences.
3. Rank decisions by how much it would hurt if the developer did NOT
   understand them — in a review, an incident, or when changing the code
   later. Weigh correctness, reliability, and security above architecture,
   performance, and maintainability, adjusted for real-world impact.

What counts as a decision — include BOTH kinds:
- Risks and trade-offs: choices with a downside someone could be asked to
  defend ("why a dict and not Redis?", "why retry 3 times?").
- Safeguards the code depends on: things done deliberately and correctly
  that a developer could easily break without realising why they exist
  (e.g. escaping user content before rendering it as HTML, holding a lock
  around a read-modify-write, bounding a cache so it can't grow forever).
  Owning code means understanding these too; for them, the consequences
  are what breaks if the safeguard is removed or bypassed.
- Gaps: cases the code's purpose implies it should handle but it doesn't,
  or error paths whose effect on data or users is easy to overlook.
- NOT style, naming, formatting, or trivia.
- NOT something the code itself makes obvious and consequence-free.

Rules for evidence and grounding:
- Line numbers in the context are the numbers at the start of each line;
  cite them as path:line or path:start-end.
- Every consequence must follow from code you can see. If something is
  missing from the context (e.g. you cannot see how a config value is set
  in production), frame it as an assumption to question, and lower confidence.
- Do not invent files, functions, or behaviour.

Rules for questions:
- Pose a concrete scenario and ask the developer to walk through what
  happens ("Two requests arrive at the same moment... what ends up in the
  database?"), rather than asking "why did you choose X?".
- Aim the scenario at the decision's MOST important consequence — the one
  a reviewer would expect the developer to know — not an edge case or a
  contrived setup (no "suppose the clock jumps back at exactly the moment...").
  A developer who understands the decision should be able to answer it.
- Never state the consequence or the fix inside the question or the setup.
- One decision per question. Answerable in a few sentences.
- The hint nudges toward where to look or what to consider, without
  giving the answer.

{already_owned}
Return up to {max_decisions} decisions, ranked. Only the top few are asked
immediately and the rest are kept for later, so be thorough rather than
terse — but every decision must be real and consequential. Return an
empty list if nothing is worth asking about.

Scope: {scope_label}

Code:
{context}
"""

GRADE_PROMPT = """\
You are grading whether a developer understands a design decision in their
own codebase (code they may not have written themselves).

Decision: {title}
Location: {location}
What the code does: {chosen}
Consequences / trade-offs:
{consequences}
Reference answer: {reference_answer}

Question asked: {question}

Developer's answer{attempt_note}:
{answer}

The reference answer is ONE good answer, not the only one. Grade what the
developer demonstrates about the question asked:

- "owned": they correctly explain what happens in the question's scenario
  and why — naming a central consequence or trade-off. It may be any of
  the listed consequences, or another one that is correct and central to
  the question. Informal wording and missing secondary details are fine.
- "partial": what they say is correct but stays surface-level — it
  restates what the code does, or gestures at a problem without saying
  what actually happens or why.
- "missing": any central claim is factually wrong about this code (even
  if other parts are right), the answer is off-topic, or they don't know.

Judge against the code's actual behaviour: an answer that sounds
plausible but contradicts the code is "missing", not "partial".

Feedback rules:
- Speak directly to the developer ("you"), 1–3 sentences.
- If owned: confirm briefly and add one short insight they didn't mention.
- If partial or missing: say what is right (if anything) and nudge toward
  the gap WITHOUT stating the answer. They may try again.
"""


def extract_decisions(context, scope_label, max_decisions=MAX_DECISIONS, owned_titles=()):
  already_owned = ""
  if owned_titles:
    listed = "\n".join(f"- {t}" for t in owned_titles)
    already_owned = (
      "The developer has already demonstrated ownership of these decisions; "
      "do not return them again unless the code for them has changed:\n"
      f"{listed}\n"
    )

  prompt = EXTRACT_PROMPT.format(
    already_owned=already_owned,
    max_decisions=max_decisions,
    scope_label=scope_label,
    context=context,
  )
  return parse(prompt, DecisionSet).decisions


def grade_answer(decision, answer, attempt=1):
  prompt = GRADE_PROMPT.format(
    title=decision.title,
    location=decision.location,
    chosen=decision.chosen,
    consequences="\n".join(f"- {c}" for c in decision.consequences),
    reference_answer=decision.reference_answer,
    question=decision.question,
    attempt_note=f" (attempt {attempt})" if attempt > 1 else "",
    answer=answer,
  )
  return parse(prompt, Grade)
