"""Run the mentor pipeline against the benchmark and score it.

  python -m evals.run                      # all projects, 3 runs, config "baseline"
  python -m evals.run --config repo-map --runs 5
  python -m evals.run --projects link-shortener --runs 1
  python -m evals.run --suite change        # review only each project's follow-up change

Writes one JSON line per (project, run) to evals/results/ and prints a
summary. Compare two result files with `python -m evals.compare`.
"""

import argparse
import json
import os
import statistics
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from mentor.llm import ensure_api_key, grade_answer, model_name
from mentor.pipeline import analyze
from mentor import git
from mentor.scope import _diff_scope, _whole_repo
from evals.benchmark import load_projects, project_repo
from evals.judge import judge_model, match_decisions, score_questions

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "evals" / "results"
TOP_K = 3
EXPECTED_VERDICT = {"good": "owned", "partial": "partial", "wrong": "missing"}
QUALITY_CRITERIA = ["grounded", "important", "non_leaking", "specific", "answerable"]

# metric → (column header, format) in display order
METRICS = {
  "recall_must_at_k": (f"Must@{TOP_K}", "pct"),
  "recall_must": ("Must(any)", "pct"),
  "recall_all": ("Recall", "pct"),
  "precision": ("Precision", "pct"),
  "quality": ("Quality/5", "num"),
  "non_leaking": ("No-leak/5", "num"),
  "central": ("Central/5", "num"),
  "grader_agreement": ("Grader", "pct"),
  "drop_rate": ("Dropped", "pct"),
}

console = Console(highlight=False)


def main():
  parser = argparse.ArgumentParser(prog="python -m evals.run")
  parser.add_argument("--config", default="baseline", help="name recorded with the results")
  parser.add_argument("--runs", type=int, default=3, help="runs per project (LLM output varies)")
  parser.add_argument("--projects", help="comma-separated subset of projects")
  parser.add_argument("--suite", choices=["whole", "change"], default="whole",
                      help="whole: review whole repos; change: review only each follow-up change")
  parser.add_argument("--grader-runs", type=int, default=1, help="runs that also test the grader (costly)")
  parser.add_argument("--jobs", type=int, default=4, help="runs evaluated in parallel (default 4)")
  args = parser.parse_args()

  ensure_api_key()
  projects = load_projects(args.projects.split(",") if args.projects else None, suite=args.suite)
  RESULTS_DIR.mkdir(exist_ok=True)
  out_path = RESULTS_DIR / f"{datetime.now():%Y-%m-%d-%H%M}-{args.config}.jsonl"
  meta = {
    "config": args.config,
    "suite": args.suite,
    "model": model_name(),
    "judge_model": judge_model() or model_name(),
    "mentor_commit": _mentor_commit(),
  }

  jobs = [(project, run) for project in projects for run in range(1, args.runs + 1)]
  console.print(f"[bold]Eval[/] {args.config} ({args.suite}) · {len(projects)} project(s) × {args.runs} run(s) · "
                f"{args.jobs} in parallel · model {meta['model']}")

  # Separate processes, not threads: each run chdirs into its own temp repo,
  # and the working directory is process-wide.
  rows = []
  with out_path.open("w") as out, ProcessPoolExecutor(max_workers=args.jobs) as pool:
    futures = {pool.submit(evaluate, project, run, run <= args.grader_runs): (project, run) for project, run in jobs}
    with console.status(f"0/{len(jobs)} runs done…") as status:
      for future in as_completed(futures):
        project, run = futures[future]
        row = future.result()
        row.update(meta)
        out.write(json.dumps(row) + "\n")
        out.flush()
        rows.append(row)
        console.print(f"  {project.name} run {run}: " + _inline(row["metrics"]))
        status.update(f"{len(rows)}/{len(jobs)} runs done…")

  rows.sort(key=lambda r: (r["project"], r["run"]))
  print_summary(rows, title=f"{args.config}  ({out_path.name})")


def evaluate(project, run, test_grader):
  started = time.time()
  cwd = os.getcwd()
  with project_repo(project) as repo:
    os.chdir(repo)
    try:
      analysis = analyze(_change_scope() if project.change else _whole_repo())
    finally:
      os.chdir(cwd)

  predicted = _unique_ids(analysis.decisions)
  labels = project.decisions
  code = analysis.context_text

  with ThreadPoolExecutor(max_workers=2) as pool:
    matches_future = pool.submit(match_decisions, labels, predicted, code)
    quality_future = pool.submit(score_questions, predicted, code)
    matches, quality = matches_future.result(), quality_future.result()

  grader = run_grader(labels, predicted, matches) if test_grader else []
  metrics = compute_metrics(labels, predicted, analysis, matches, quality, grader)
  metrics["seconds"] = round(time.time() - started, 1)

  return {
    "project": project.name,
    "verified": project.verified,
    "run": run,
    "metrics": metrics,
    "predicted": [
      {"rank": i + 1, "id": d.id, "title": d.title, "location": d.location, "category": d.category,
       "confidence": d.confidence, "question": d.question,
       "label": m.label_id, "real": m.is_real_decision, "judge_reason": m.reason,
       "decision": d.model_dump()}  # full answer key, so the grader can be replayed offline
      for i, (d, m) in enumerate(zip(predicted, matches))
    ],
    "dropped": [{"title": d.title, "location": d.location, "reason": r} for d, r in analysis.dropped],
    "quality": [q.model_dump() for q in quality],
    "grader": grader,
  }


def _change_scope():
  """The last commit only — what `mentor review` covers after one change."""
  return _diff_scope(git.git("rev-parse", "HEAD~1").strip(), "last commit")


def run_grader(labels, predicted, matches):
  """Grade each label's sample answers against the mentor's own answer key."""
  decision_for_label = {}
  for d, m in zip(predicted, matches):
    if m.label_id and m.label_id not in decision_for_label:
      decision_for_label[m.label_id] = d

  jobs = [
    (label.id, kind, decision_for_label[label.id], getattr(label.answers, kind))
    for label in labels if label.id in decision_for_label
    for kind in EXPECTED_VERDICT
  ]
  with ThreadPoolExecutor(max_workers=6) as pool:
    grades = list(pool.map(lambda job: grade_answer(job[2], job[3]), jobs))

  return [
    {"label": label_id, "answer": kind, "expected": EXPECTED_VERDICT[kind], "got": grade.verdict}
    for (label_id, kind, _, _), grade in zip(jobs, grades)
  ]


def compute_metrics(labels, predicted, analysis, matches, quality, grader):
  must = {l.id for l in labels if l.priority == "must-find"}
  matched_all = {m.label_id for m in matches if m.label_id}
  matched_top = {m.label_id for m in matches[:TOP_K] if m.label_id}

  metrics = {
    "labels": len(labels),
    "found": len(analysis.found),
    "kept": len(predicted),
    # normalised by min(k, |must|) so a perfect top-k scores 100% even with >k must-finds
    "recall_must_at_k": _ratio(len(must & matched_top), min(TOP_K, len(must))),
    "recall_must": _ratio(len(must & matched_all), len(must)),
    "recall_all": _ratio(len(matched_all), len(labels)),
    "precision": _ratio(sum(m.is_real_decision for m in matches), len(matches)),
    "drop_rate": _ratio(len(analysis.dropped), len(analysis.found)),
    "grader_agreement": _ratio(sum(g["expected"] == g["got"] for g in grader), len(grader)) if grader else None,
  }
  if quality:
    per_criterion = {c: statistics.mean(getattr(q, c) for q in quality) for c in QUALITY_CRITERIA}
    metrics["quality"] = round(statistics.mean(per_criterion.values()), 2)
    metrics["non_leaking"] = round(per_criterion["non_leaking"], 2)
    # reported separately (added later) so "quality" stays comparable across runs
    centrals = [q.central for q in quality if q.central is not None]
    metrics["central"] = round(statistics.mean(centrals), 2) if centrals else None
  else:
    metrics["quality"] = metrics["non_leaking"] = metrics["central"] = None
  return metrics


# ── summary ───────────────────────────────────────────────────────────────

def aggregate(rows):
  """{project or 'ALL': {metric: (mean, stdev, n)}}"""
  groups = {}
  for row in rows:
    groups.setdefault(row["project"], []).append(row["metrics"])
  groups["ALL"] = [row["metrics"] for row in rows]

  summary = {}
  for name, metric_rows in groups.items():
    summary[name] = {}
    for metric in METRICS:
      values = [m[metric] for m in metric_rows if m.get(metric) is not None]
      if values:
        spread = statistics.stdev(values) if len(values) > 1 else 0.0
        summary[name][metric] = (statistics.mean(values), spread, len(values))
  return summary


def print_summary(rows, title):
  summary = aggregate(rows)
  unverified = sorted({r["project"] for r in rows if not r["verified"]})

  table = Table(title=title, title_justify="left")
  table.add_column("Project")
  for header, _ in METRICS.values():
    table.add_column(header, justify="right")

  for name, values in summary.items():
    style = "bold" if name == "ALL" else ""
    label = f"{name} *" if name in unverified else name
    table.add_row(label, *[format_stat(values.get(m), fmt) for m, (_, fmt) in METRICS.items()], style=style)

  console.print()
  console.print(table)
  console.print("[dim]mean ± stdev across runs. Must@3: top-3 questions that are must-finds (of min(3, #must)). "
                "Must(any): must-finds found at any rank. "
                "Precision: kept decisions that are real. Grader: sample answers graded as labelled.[/]")
  if unverified:
    console.print(f"[yellow]* labels not yet human-verified: {', '.join(unverified)}[/]")


def format_stat(stat, fmt):
  if stat is None:
    return "—"
  mean, spread, n = stat
  if fmt == "pct":
    text = f"{mean * 100:.0f}%"
    return text + (f" ±{spread * 100:.0f}" if n > 1 else "")
  text = f"{mean:.2f}"
  return text + (f" ±{spread:.2f}" if n > 1 else "")


def _inline(metrics):
  parts = []
  for metric, (header, fmt) in METRICS.items():
    value = metrics.get(metric)
    if value is not None:
      parts.append(f"{header} {value * 100:.0f}%" if fmt == "pct" else f"{header} {value:.2f}")
  return " · ".join(parts) + f" · {metrics['seconds']}s"


def _ratio(numerator, denominator):
  return round(numerator / denominator, 3) if denominator else None


def _unique_ids(decisions):
  seen = {}
  for d in decisions:
    if d.id in seen:
      seen[d.id] += 1
      d.id = f"{d.id}-{seen[d.id]}"
    else:
      seen[d.id] = 1
  return decisions


def _mentor_commit():
  try:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                         cwd=ROOT, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "mentor"], capture_output=True, text=True,
                           cwd=ROOT).stdout.strip()
    return sha + ("-dirty" if dirty else "")
  except subprocess.CalledProcessError:
    return None


if __name__ == "__main__":
  main()
