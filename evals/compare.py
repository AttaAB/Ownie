"""Compare two eval result files side by side.

  python -m evals.compare baseline repo-map        # latest file for each config
  python -m evals.compare evals/results/A.jsonl evals/results/B.jsonl
"""

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from evals.run import METRICS, RESULTS_DIR, aggregate, format_stat

console = Console(highlight=False)


def main():
  parser = argparse.ArgumentParser(prog="python -m evals.compare")
  parser.add_argument("a", help="config name or result file (the 'before')")
  parser.add_argument("b", help="config name or result file (the 'after')")
  args = parser.parse_args()

  path_a, path_b = resolve(args.a), resolve(args.b)
  a, b = aggregate(load(path_a)), aggregate(load(path_b))

  for project in [p for p in a if p in b and p != "ALL"] + ["ALL"]:
    table = Table(title=project, title_justify="left")
    table.add_column("Metric")
    table.add_column(path_a.stem, justify="right")
    table.add_column(path_b.stem, justify="right")
    table.add_column("Δ", justify="right")

    for metric, (header, fmt) in METRICS.items():
      before, after = a[project].get(metric), b[project].get(metric)
      table.add_row(header, format_stat(before, fmt), format_stat(after, fmt), delta(before, after, fmt, metric))
    console.print(table)


def delta(before, after, fmt, metric):
  if before is None or after is None:
    return ""
  change = after[0] - before[0]
  better = change < 0 if metric == "drop_rate" else change > 0
  text = f"{change * 100:+.0f}pt" if fmt == "pct" else f"{change:+.2f}"
  if abs(change) < 1e-9:
    return f"[dim]{text}[/]"
  return f"[green]{text}[/]" if better else f"[red]{text}[/]"


def resolve(name):
  path = Path(name)
  if path.exists():
    return path
  # files are "<YYYY-MM-DD-HHMM>-<config>.jsonl"; match the config exactly, so
  # "ranking-v6" doesn't also pick up "change-ranking-v6"
  candidates = sorted(p for p in RESULTS_DIR.glob(f"*-{name}.jsonl") if p.stem[16:] == name)
  if not candidates:
    raise SystemExit(f"No results found for {name!r} in {RESULTS_DIR}")
  return candidates[-1]


def load(path):
  return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


if __name__ == "__main__":
  main()
