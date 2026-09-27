"""Load benchmark cases and materialize them as throwaway git repos.

Two suites:
  whole   — benchmark/<project>/labels.yaml; the whole repo is reviewed
  change  — benchmark/<project>/changes/<name>/{change.patch,labels.yaml};
            the project is committed, the patch applied as a second commit,
            and only that commit is reviewed (like `mentor review` after a change)

  python -m evals.benchmark --check     # every label's path:line exists
"""

import argparse
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from mentor.models import Category

BENCHMARK_DIR = Path(__file__).resolve().parent.parent / "benchmark"


class Answers(BaseModel):
  good: str
  partial: str
  wrong: str


class Label(BaseModel):
  id: str
  title: str
  location: str
  also_at: list[str] = []
  category: Category
  priority: Literal["must-find", "nice-to-find"]
  key_point: str
  answers: Answers


class Project(BaseModel):
  project: str
  change: str | None = None       # set for change-suite cases
  language: str
  verified: bool = False
  decisions: list[Label]

  @property
  def name(self):
    return f"{self.project}/{self.change}" if self.change else self.project

  @property
  def repo_dir(self):
    return BENCHMARK_DIR / self.project / "repo"

  @property
  def patch(self):
    return BENCHMARK_DIR / self.project / "changes" / self.change / "change.patch"


SUITES = {"whole": "*/labels.yaml", "change": "*/changes/*/labels.yaml"}


def load_projects(names=None, suite="whole"):
  """`names` match a project ("sync-cli") or a change case ("sync-cli/multi-folder-sync")."""
  projects = []
  for labels_file in sorted(BENCHMARK_DIR.glob(SUITES[suite])):
    project = Project(**yaml.safe_load(labels_file.read_text()))
    if names and project.project not in names and project.name not in names:
      continue
    projects.append(project)

  missing = set(names or ()) - {p.project for p in projects} - {p.name for p in projects}
  if missing:
    raise SystemExit(f"Unknown benchmark project(s): {', '.join(sorted(missing))}")
  return projects


@contextmanager
def project_repo(project):
  """Copy a project into a temp git repo and yield its path.

  One commit ("snapshot"); change cases get a second commit ("change")
  with the patch applied, so HEAD~1..HEAD is exactly the change.
  """
  with tempfile.TemporaryDirectory(prefix=f"mentor-eval-{project.project}-") as tmp:
    repo = Path(tmp) / project.project
    shutil.copytree(project.repo_dir, repo)
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "snapshot")
    if project.change:
      _git(repo, "apply", "--binary", str(project.patch))
      _commit(repo, "change")
    yield repo


def _commit(repo, message):
  _git(repo, "add", "-A")
  _git(repo, "-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-q", "-m", message)


def _git(repo, *args):
  subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


# ── label check ───────────────────────────────────────────────────────────

LOCATION = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")


def check_labels(project):
  """Problems with the project's label locations (empty list = all good).

  Change cases must cite lines the change touched or added, since those
  are what a change review shows the model.
  """
  problems = []
  with project_repo(project) as repo:
    changed = _changed_lines(repo) if project.change else None
    for label in project.decisions:
      for location in [label.location, *label.also_at]:
        match = LOCATION.match(location)
        if not match:
          problems.append(f"{label.id}: bad location {location!r}")
          continue
        path, start, end = match[1], int(match[2]), int(match[3] or match[2])
        file = repo / path
        if not file.is_file():
          problems.append(f"{label.id}: no file {path}")
          continue
        lines = len(file.read_text().splitlines())
        if not 1 <= start <= end <= lines:
          problems.append(f"{label.id}: {location} outside 1-{lines}")
        elif changed is not None and location == label.location and not changed.get(path, set()) & set(range(start, end + 1)):
          problems.append(f"{label.id}: {location} is not part of the change")
  return problems


def _changed_lines(repo):
  """{path: {line numbers added or modified in HEAD}}"""
  diff = subprocess.run(["git", "diff", "-U0", "HEAD~1", "HEAD"], cwd=repo, check=True,
                        capture_output=True, text=True).stdout
  changed, path = {}, None
  for line in diff.splitlines():
    if line.startswith("+++ "):
      path = line[6:] if line.startswith("+++ b/") else None
    elif line.startswith("@@") and path:
      start, _, count = re.match(r"@@ -\S+ \+(\d+)(,(\d+))?", line).groups()
      count = int(count) if count is not None else 1
      changed.setdefault(path, set()).update(range(int(start), int(start) + count))
  return changed


def main():
  parser = argparse.ArgumentParser(prog="python -m evals.benchmark")
  parser.add_argument("--check", action="store_true", help="validate every label's path:line")
  args = parser.parse_args()
  if not args.check:
    parser.print_help()
    return

  failed = False
  for suite in SUITES:
    for project in load_projects(suite=suite):
      problems = check_labels(project)
      failed |= bool(problems)
      print(f"{'✗' if problems else '✓'} {project.name} ({len(project.decisions)} labels)")
      for problem in problems:
        print(f"    {problem}")
  raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
  main()
