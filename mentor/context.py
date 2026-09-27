"""Turn a Scope into the text the model reads.

Session 1 is deliberately diff-only (plus full untracked files). Richer
retrieval — repo map, cross-file references, agent tools — comes in
Sessions 3–4, measured against the eval baseline.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from mentor import git as g
from mentor.scope import exclude_pathspecs

MAX_CONTEXT_CHARS = 150_000
MAX_FILE_CHARS = 40_000
MAX_GRADER_CHARS = 60_000

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
DIFF_TARGET = re.compile(r"^\+\+\+ b/(.+)$")


@dataclass
class Context:
  text: str
  truncated: bool
  # path → line numbers the model was shown; used to verify its citations
  visible_lines: dict[str, set[int]] = field(default_factory=dict)


def build_context(scope):
  if scope.kind == "all":
    sections = [_numbered_file(path) for path in scope.files]
  else:
    diff = g.git("diff", scope.base, *exclude_pathspecs())
    sections = _split_diff(diff) + [_numbered_file(path, new=True) for path in scope.untracked]

  context = Context(text="", truncated=False)
  for section in sections:
    if not section:
      continue
    text, lines = section
    if len(context.text) + len(text) > MAX_CONTEXT_CHARS:
      context.truncated = True
      break
    context.text += text + "\n"
    for path, numbers in lines.items():
      context.visible_lines.setdefault(path, set()).update(numbers)

  return context


def code_for(decision):
  """The full files a decision cites, line-numbered, for the grader.

  The answer key can miss things; with the code, the grader can check a
  claim the key doesn't cover instead of calling it wrong.
  """
  paths = dict.fromkeys(ref.split(":")[0].strip() for ref in [decision.location, *decision.evidence])
  text = ""
  for path in paths:
    section = _numbered_file(path)
    if section and len(text) + len(section[0]) <= MAX_GRADER_CHARS:
      text += section[0] + "\n"
  return text


def _split_diff(diff):
  """One annotated section per file, so truncation drops whole files."""
  chunks = re.split(r"(?m)^(?=diff --git )", diff)
  return [_annotate_diff(chunk) for chunk in chunks if chunk.strip()]


def _annotate_diff(diff):
  """Prefix each line of a unified diff with its line number in the new file.

  Lets the model cite `file:line` locations instead of guessing from hunk
  headers. Removed lines get no number because they no longer exist.
  Returns (text, {path: visible line numbers}).
  """
  out = []
  lines = {}
  path = None
  new_line = 0
  in_hunk = False

  for line in diff.splitlines():
    if line.startswith("diff --git"):
      out.append("")
      out.append(line)
      in_hunk = False
      continue

    header = HUNK_HEADER.match(line)
    if header:
      new_line = int(header.group(1))
      in_hunk = True
      out.append(line)
    elif not in_hunk:
      # file metadata: index, ---/+++ paths, mode, rename, binary markers
      target = DIFF_TARGET.match(line)
      if target:
        path = target.group(1)
        lines.setdefault(path, set())
      out.append(line)
    elif line.startswith("+"):
      out.append(f"{new_line:>5} +{line[1:]}")
      lines.get(path, set()).add(new_line)
      new_line += 1
    elif line.startswith("-"):
      out.append(f"      -{line[1:]}")
    elif line.startswith("\\"):
      continue  # "\ No newline at end of file"
    else:
      out.append(f"{new_line:>5}  {line[1:]}")
      lines.get(path, set()).add(new_line)
      new_line += 1

  return "\n".join(out), lines


def _numbered_file(path, new=False):
  try:
    content = Path(path).read_text(encoding="utf-8")
  except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
    return None  # binary, deleted, or not a regular file

  if len(content) > MAX_FILE_CHARS:
    content = content[:MAX_FILE_CHARS] + "\n... (file truncated)"

  marker = "+" if new else " "
  header = f"\nNew untracked file: {path}" if new else f"\nFile: {path}"
  source_lines = content.splitlines()
  numbered = "\n".join(f"{i:>5} {marker}{line}" for i, line in enumerate(source_lines, start=1))
  return f"{header}\n{numbered}", {path: set(range(1, len(source_lines) + 1))}
