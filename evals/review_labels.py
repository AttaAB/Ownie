"""Review the change suite's labels: you are the ground truth.

  python -m evals.review_labels        # review every unreviewed label, then apply

For each label it shows the code (changed lines highlighted), the claim,
and the sample answers — but not the suggested priority, so your call
isn't anchored on the AI's. Keys:

  m must-find   n nice-to-find   x not a real decision (remove)
  c the claim or answers are wrong → type a note, then m/n/x
  q quit (progress saved; run again to resume)

Reviews are appended to evals/label_reviews.jsonl. Once every label in a
change is reviewed, its labels.yaml is updated (priorities set, rejected
labels removed) and — if you left no notes — marked `verified: true`.
Notes are left for Claude to resolve.
"""

import json
import random
import re
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from evals.benchmark import BENCHMARK_DIR, LOCATION, _changed_lines, check_labels, load_projects, project_repo

REVIEWS_FILE = Path(__file__).resolve().parent / "label_reviews.jsonl"
KEYS = {"m": "must-find", "n": "nice-to-find", "x": "remove"}
CONTEXT_LINES = 3
MAX_SNIPPET_LINES = 40

console = Console(highlight=False)


def main():
  console.print(Text.assemble(
    ("Review each label as the developer who'd have to explain this change in its code review.\n", "bold"),
    ("  m must-find — I'd be embarrassed not to be able to explain it   n nice-to-find — real, secondary\n"
     "  x not a real decision (remove)   c claim or answers wrong (add a note)   q quit (progress saved)", "dim")))

  for project in load_projects(suite="change"):
    done = _reviews(project.name)
    todo = [label for label in project.decisions if label.id not in done]
    random.Random(project.name).shuffle(todo)  # file order puts suggested must-finds first
    if todo and not review_change(project, todo, len(done)):
      return
    apply(project)

  console.print("\nAll change labels reviewed.")


def review_change(project, todo, already):
  """Review `todo` labels; False if the user quit."""
  with project_repo(project) as repo:
    changed = _changed_lines(repo)
    stat = subprocess.run(["git", "diff", "--stat", "HEAD~1", "HEAD"], cwd=repo,
                          capture_output=True, text=True).stdout.rstrip()
    console.print()
    console.rule(f"[bold]{project.name}[/]")
    request = _feature_request(project)
    if request:
      console.print(Text.assemble(("Feature request: ", "bold"), (request, "italic")))
    console.print(Text(stat, style="dim"))

    total = len(project.decisions)
    for i, label in enumerate(todo, already + 1):
      show(label, repo, changed, f"{i}/{total}")
      verdict = ask_verdict()
      if verdict is None:
        return False
      _save({"change": project.name, "id": label.id, **verdict})

  if not _reviews(project.name, missing=True):
    missing = console.input("\n[bold cyan]Anything important in this change that isn't labelled?[/] "
                            "[dim](describe it, or Enter for nothing) ›[/] ").strip()
    _save({"change": project.name, "id": None, "missing": missing})
  return True


def show(label, repo, changed, progress):
  match = LOCATION.match(label.location)
  path, start, end = match[1], int(match[2]), int(match[3] or match[2])
  lines = (repo / path).read_text().splitlines()
  first = max(1, start - CONTEXT_LINES)
  last = min(len(lines), end + CONTEXT_LINES, first + MAX_SNIPPET_LINES - 1)
  snippet = "\n".join(lines[first - 1:last])
  code = Syntax(snippet, Syntax.guess_lexer(path, code=snippet), line_numbers=True, start_line=first,
                highlight_lines=changed.get(path, set()) & set(range(first, last + 1)), word_wrap=True)

  console.print()
  console.print(Panel(code, title=f" {label.location} ", title_align="left", subtitle=f" {progress} ",
                      subtitle_align="right", width=min(console.width, 110)))
  if label.also_at:
    console.print(Text(f"also at: {', '.join(label.also_at)}", style="dim"))
  console.print(Text.assemble(("Decision  ", "bold cyan"), (label.title, "bold"), f"  [{label.category}]"))
  console.print(Text.assemble(("Claim     ", "bold cyan"), " ".join(label.key_point.split())))
  for kind, style in (("good", "green"), ("partial", "yellow"), ("wrong", "red")):
    answer = " ".join(getattr(label.answers, kind).split())
    console.print(Text.assemble((f"{kind:<10}", style), (answer, "dim")))


def ask_verdict():
  """{"priority": ..., "note": ...}, or None to quit."""
  note = ""
  while True:
    choice = console.input("[bold cyan]m/n/x/c ›[/] ").strip().lower()
    if choice == "q":
      return None
    if choice == "c":
      note = console.input("[dim]what's wrong? ›[/] ").strip()
      console.print("[dim]and its priority (or x if it isn't real):[/]")
      continue
    if choice in KEYS:
      return {"priority": KEYS[choice], "note": note}


def apply(project):
  """Write the reviews for a fully reviewed change into its labels.yaml."""
  reviews = _reviews(project.name)
  path = BENCHMARK_DIR / project.project / "changes" / project.change / "labels.yaml"
  text = path.read_text()
  for label_id, review in reviews.items():
    if review["priority"] == "remove":
      text = _remove_block(text, label_id)
    else:
      text = _set_priority(text, label_id, review["priority"])

  notes = [f"{i}: {r['note']}" for i, r in reviews.items() if r.get("note")]
  missing = _reviews(project.name, missing=True)
  if missing and missing.get("missing"):
    notes.append(f"missing: {missing['missing']}")
  if not notes:
    text = re.sub(r"(?m)^verified: .*$", "verified: true", text)
  path.write_text(text)

  kept = sum(r["priority"] != "remove" for r in reviews.values())
  must = sum(r["priority"] == "must-find" for r in reviews.values())
  problems = check_labels(load_projects([project.name], suite="change")[0])
  status = "[green]verified[/]" if not notes else f"[yellow]{len(notes)} note(s) for Claude to resolve[/]"
  console.print(f"\n{project.name}: {kept} labels ({must} must-find) · {status}"
                + ("" if not problems else f" · [red]check failed: {problems}[/]"))


def _remove_block(text, label_id):
  lines = text.splitlines(keepends=True)
  starts = [i for i, line in enumerate(lines) if re.match(r"  - id: ", line)]
  for n, start in enumerate(starts):
    if lines[start].strip() == f"- id: {label_id}":
      end = starts[n + 1] if n + 1 < len(starts) else len(lines)
      return "".join(lines[:start] + lines[end:])
  return text  # already removed


def _set_priority(text, label_id, priority):
  pattern = rf"(?ms)(^  - id: {re.escape(label_id)}\n.*?^    priority: )\S+"
  return re.sub(pattern, rf"\g<1>{priority}", text, count=1)


def _feature_request(project):
  path = BENCHMARK_DIR / project.project / "changes" / project.change / "labels.yaml"
  quoted = re.findall(r"(?m)^#\s{3}(.*)$", path.read_text())
  return " ".join(line.strip() for line in quoted).strip('"')


def _reviews(change, missing=False):
  """{label_id: review} for a change, or its "missing" entry if `missing`."""
  found = {}
  if REVIEWS_FILE.exists():
    for line in REVIEWS_FILE.read_text().splitlines():
      if line.strip():
        r = json.loads(line)
        if r["change"] == change:
          found[r["id"]] = r
  if missing:
    return found.get(None)
  found.pop(None, None)
  return found


def _save(review):
  with REVIEWS_FILE.open("a") as f:
    f.write(json.dumps(review) + "\n")


if __name__ == "__main__":
  main()
