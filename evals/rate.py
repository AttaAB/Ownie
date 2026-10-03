"""Hand-rate Ownie's questions, to calibrate the LLM judge against a human.

  python -m evals.rate                 # rate 20 questions sampled from the latest results
  python -m evals.rate -n 30 --results questions-v3
  python -m evals.rate --report        # judge-vs-human agreement

Ratings are appended to evals/human_ratings.jsonl (one line per question),
so you can stop any time and resume later — already-rated questions are
skipped.
"""

import argparse
import json
import random
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from evals.compare import load, resolve
from evals.run import RESULTS_DIR

RATINGS_FILE = Path(__file__).resolve().parent / "human_ratings.jsonl"
KEYS = {"g": "good", "o": "okay", "b": "bad"}

console = Console(highlight=False)


def main():
  parser = argparse.ArgumentParser(prog="python -m evals.rate")
  parser.add_argument("-n", type=int, default=20, help="questions to rate this session")
  parser.add_argument("--results", help="config name or results file (default: latest)")
  parser.add_argument("--report", action="store_true", help="show judge-vs-human agreement")
  args = parser.parse_args()

  if args.report:
    return report()

  path = resolve(args.results) if args.results else max(RESULTS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
  rated = {r["key"] for r in _ratings()}
  pool = []
  for row in load(path):
    quality = {q["predicted_id"]: q for q in row.get("quality", [])}
    for p in row["predicted"]:
      key = f"{path.name}:{row['project']}:{row['run']}:{p['id']}"
      if key not in rated and p["id"] in quality:
        pool.append((key, row["project"], p, quality[p["id"]]))

  random.Random(7).shuffle(pool)
  batch = pool[:args.n]
  if not batch:
    console.print("Nothing left to rate in that results file.")
    return

  console.print(Text.assemble(("Rate each question as a developer who has to own this code.\n", "bold"),
                              ("  g good — I'd want to be asked this   o okay — fine but not great   "
                               "b bad — contrived, trivial, leaks the answer, or wrong\n  q quit (progress saved)", "dim")))

  for i, (key, project, p, judge) in enumerate(batch, 1):
    body = Text.assemble((p["decision"]["setup"] + "\n\n", "dim"), ("Q  ", "bold cyan"), (p["question"], "bold"))
    console.print()
    console.print(Panel(body, title=f" {project} · {p['location']} ", title_align="left",
                        subtitle=f" {i}/{len(batch)} ", subtitle_align="right", width=min(console.width, 88)))
    while True:
      choice = console.input("[bold cyan]g/o/b ›[/] ").strip().lower()
      if choice == "q":
        return
      if choice in KEYS:
        break
    note = console.input("[dim]note (optional, Enter to skip) ›[/] ").strip()
    with RATINGS_FILE.open("a") as f:
      f.write(json.dumps({"key": key, "project": project, "question": p["question"], "human": KEYS[choice],
                          "note": note, "judge": {k: judge.get(k) for k in
                          ("grounded", "important", "non_leaking", "specific", "answerable", "central")}}) + "\n")

  console.print("\nThanks — saved. Run `python -m evals.rate --report` to see how the judge compares.")


def report():
  ratings = _ratings()
  if not ratings:
    console.print("No ratings yet.")
    return

  def judge_mean(r):
    scores = [v for v in r["judge"].values() if v is not None]
    return sum(scores) / len(scores)

  console.print(f"[bold]{len(ratings)} human ratings[/]")
  for label in ("good", "okay", "bad"):
    group = [judge_mean(r) for r in ratings if r["human"] == label]
    if group:
      console.print(f"  human {label:<5} n={len(group):<3} judge mean {sum(group) / len(group):.2f}/5")

  # A useful judge scores human-"bad" questions clearly below human-"good" ones.
  good = [judge_mean(r) for r in ratings if r["human"] == "good"]
  bad = [judge_mean(r) for r in ratings if r["human"] == "bad"]
  if good and bad:
    pairs = [(g, b) for g in good for b in bad]
    separation = sum(1 for g, b in pairs if g > b) + 0.5 * sum(1 for g, b in pairs if g == b)
    console.print(f"  judge ranks a human-good question above a human-bad one {separation / len(pairs):.0%} of the time "
                  "[dim](50% = no better than chance)[/]")


def _ratings():
  if not RATINGS_FILE.exists():
    return []
  return [json.loads(line) for line in RATINGS_FILE.read_text().splitlines() if line.strip()]


if __name__ == "__main__":
  main()
