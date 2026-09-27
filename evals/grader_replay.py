"""Re-grade the benchmark's sample answers against saved answer keys.

A normal eval run regenerates decisions, so grader changes get mixed up
with extraction noise. This replays the grader on the exact answer keys
stored in a results file (every run, not just run 1), so two grader
versions can be compared on identical inputs:

  python -m evals.grader_replay grader-v2          # latest results for a config
  python -m evals.grader_replay evals/results/X.jsonl
"""

import argparse
import collections
from concurrent.futures import ThreadPoolExecutor

from rich.console import Console
from rich.table import Table

from mentor.llm import ensure_api_key, grade_answer
from mentor.models import Decision
from evals.benchmark import load_projects
from evals.compare import load, resolve
from evals.run import EXPECTED_VERDICT

console = Console(highlight=False)


def main():
  parser = argparse.ArgumentParser(prog="python -m evals.grader_replay")
  parser.add_argument("results", help="config name or results file with stored answer keys")
  args = parser.parse_args()

  ensure_api_key()
  path = resolve(args.results)
  projects = load_projects(suite="whole") + load_projects(suite="change")
  labels = {p.name: {d.id: d for d in p.decisions} for p in projects}

  jobs = []
  for row in load(path):
    used = set()
    for predicted in row["predicted"]:
      label_id = predicted.get("label")
      if not label_id or label_id in used or "decision" not in predicted:
        continue
      used.add(label_id)
      decision = Decision(**predicted["decision"])
      label = labels[row["project"]][label_id]
      for kind, expected in EXPECTED_VERDICT.items():
        jobs.append((row["project"], label_id, kind, expected, decision, getattr(label.answers, kind)))

  if not jobs:
    raise SystemExit(f"{path.name} has no stored answer keys (results before answer keys were saved).")

  with console.status(f"Grading {len(jobs)} answers…"):
    with ThreadPoolExecutor(max_workers=8) as pool:
      verdicts = list(pool.map(lambda j: grade_answer(j[4], j[5]).verdict, jobs))

  confusion = collections.Counter((j[3], v) for j, v in zip(jobs, verdicts))
  agree = sum(n for (expected, got), n in confusion.items() if expected == got)

  table = Table(title=f"Grader replay · {path.name} · {len(jobs)} answers", title_justify="left")
  table.add_column("expected ↓ / got →")
  for got in ("owned", "partial", "missing"):
    table.add_column(got, justify="right")
  for expected in ("owned", "partial", "missing"):
    table.add_row(expected, *[str(confusion[(expected, got)]) for got in ("owned", "partial", "missing")])
  console.print(table)
  console.print(f"[bold]Agreement {agree / len(jobs):.0%}[/] ({agree}/{len(jobs)})")

  for j, v in zip(jobs, verdicts):
    if j[3] != v:
      console.print(f"[dim]  {j[0]}/{j[1]} {j[2]} answer: expected {j[3]}, got {v}[/]")


if __name__ == "__main__":
  main()
