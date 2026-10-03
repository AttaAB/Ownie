"""Thin wrapper around the git command line."""

import subprocess


class GitError(Exception):
  pass


def git(*args, cwd=None):
  result = subprocess.run(
    ["git", *args],
    cwd=cwd,
    capture_output=True,
    text=True,
  )
  if result.returncode != 0:
    raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
  return result.stdout


def repo_root():
  return git("rev-parse", "--show-toplevel").strip()


def current_branch():
  return git("rev-parse", "--abbrev-ref", "HEAD").strip()


def head_commit():
  try:
    return git("rev-parse", "HEAD").strip()
  except GitError:
    return None  # repo with no commits yet


def ref_exists(ref):
  try:
    git("rev-parse", "--verify", "--quiet", ref)
    return True
  except GitError:
    return False


def default_branch():
  for name in ("main", "master"):
    if ref_exists(name):
      return name
  return None


def is_ancestor(ancestor, descendant="HEAD"):
  try:
    git("merge-base", "--is-ancestor", ancestor, descendant)
    return True
  except GitError:
    return False


def untracked_files():
  return [f for f in git("ls-files", "--others", "--exclude-standard").splitlines() if f]


def tracked_files():
  return [f for f in git("ls-files").splitlines() if f]


def has_uncommitted_changes():
  return bool(git("status", "--porcelain").strip())


def short(sha):
  return sha[:7] if sha else "∅"
