from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
  "correctness",
  "reliability",
  "security",
  "architecture",
  "performance",
  "maintainability",
]

Verdict = Literal["owned", "partial", "missing"]


class Decision(BaseModel):
  """One implicit design decision, with its hidden answer key.

  Everything except `setup` and `question` stays hidden until the
  developer has answered.
  """

  id: str = Field(description="short kebab-case slug, e.g. 'in-memory-rate-limit'")
  title: str = Field(description="one line naming the decision")
  category: Category
  location: str = Field(description="primary location as path:start-end")

  # answer key
  chosen: str = Field(description="what the code does / the approach taken")
  alternatives: list[str] = Field(description="realistic approaches that were not taken")
  consequences: list[str] = Field(description="concrete consequences and trade-offs of the chosen approach")
  evidence: list[str] = Field(description="path:line references that support the claims above")
  confidence: float = Field(description="0-1, how sure you are this decision and its consequences are real")

  # what the developer sees
  setup: str = Field(description="one neutral sentence describing what the code does, without judging it")
  question: str = Field(description="the Socratic question; must not reveal the consequence")
  hint: str = Field(description="a nudge toward the answer that still does not state it")
  reference_answer: str = Field(description="what a developer who owns this decision would say")


class DecisionSet(BaseModel):
  decisions: list[Decision] = Field(description="ranked, most important first")


class Grade(BaseModel):
  verdict: Verdict
  feedback: str = Field(
    description="if owned: confirm briefly and add one insight. "
                "if partial/missing: acknowledge what is right and nudge "
                "toward the gap without stating the answer"
  )
