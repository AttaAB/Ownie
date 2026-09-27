"""Everything the user sees. Logic lives elsewhere; this module only renders.

Built on rich, which degrades to plain text when output isn't a terminal
(pipes, CI), so the same code serves both.
"""

from pathlib import Path

from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mentor.verify import parse_refs

console = Console(highlight=False)

WIDTH = 88
MAX_SNIPPET_LINES = 14

CATEGORY_COLORS = {
  "correctness": "red",
  "reliability": "dark_orange",
  "security": "magenta",
  "architecture": "blue",
  "performance": "cyan",
  "maintainability": "green",
}

VERDICTS = {
  "owned": ("✓ Owned", "bold green"),
  "partial": ("◐ Partial", "bold yellow"),
  "missing": ("✗ Not quite", "bold red"),
}


def _width():
  return min(console.width, WIDTH)


# ── small pieces ──────────────────────────────────────────────────────────

def info(text):
  console.print(text)


def note(text):
  console.print(Text(f"  {text}", style="dim"))


def step(verbose, name, detail):
  if verbose:
    console.print(Text(f"▸ {name:<10} {detail}", style="dim"))


def working(message):
  """Spinner shown while waiting on the model."""
  return console.status(Text(message, style="dim"), spinner="dots")


def prompt():
  return console.input("[bold cyan]›[/] ")


def controls(again=False):
  lead = "Answer again" if again else "Type your answer"
  console.print(Text(f"  {lead}, or  h hint · e explain · s skip · q quit", style="dim"))


# ── review flow ───────────────────────────────────────────────────────────

def choice_menu(question, options):
  console.print()
  console.print(Text(question, style="bold"))
  for number, (_, label) in enumerate(options, start=1):
    console.print(f"  [cyan]{number}[/]  {label}")


def found(count, asked, scope_label):
  console.print()
  headline = Text.assemble(("Found ", ""), (str(count), "bold"), (f" design decision{'s' if count != 1 else ''} in ", ""), (scope_label, "italic"))
  console.print(headline)
  if count > asked:
    console.print(Text(f"Here are the {asked} you'd most likely be asked to explain.", style="dim"))


def question_card(decision, number, total):
  color = CATEGORY_COLORS.get(decision.category, "white")
  parts = []

  snippet = code_snippet(decision.location)
  if snippet is not None:
    parts += [snippet, Text("")]

  question = Table.grid(padding=(0, 2))
  question.add_row(Text("Q", style=f"bold {color}"), Text(decision.question, style="bold"))

  parts += [Text(decision.setup, style="dim"), Text(""), question]

  console.print()
  console.print(Panel(
    Group(*parts),
    title=Text.assemble((f" {decision.category} ", f"bold {color}"), (f"· {decision.location} ", "")),
    title_align="left",
    subtitle=Text(f" {number}/{total} ", style="dim"),
    subtitle_align="right",
    border_style=color,
    padding=(1, 2),
    width=_width(),
  ))


def code_snippet(location):
  """The cited lines from the working tree, syntax-highlighted, or None."""
  refs = list(parse_refs(location))
  if not refs:
    return None
  path, start, end = refs[0]

  try:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
  except (OSError, UnicodeDecodeError):
    return None
  if start > len(lines):
    return None

  end = min(end, len(lines))
  while start < end and not lines[start - 1].strip():
    start += 1
  while end > start and not lines[end - 1].strip():
    end -= 1
  end = min(end, start + MAX_SNIPPET_LINES - 1)
  code = "\n".join(lines[start - 1:end])
  return Syntax(
    code,
    Syntax.guess_lexer(path, code),
    line_numbers=True,
    start_line=start,
    theme="ansi_dark",
    background_color="default",
    word_wrap=False,
  )


def _labelled(label, style, text):
  row = Table.grid(padding=(0, 2))
  row.add_column(width=11)
  row.add_row(Text(label, style=style), Text(text))
  console.print(Padding(row, (0, 2)), width=_width())


def verdict(grade):
  label, style = VERDICTS[grade.verdict]
  _labelled(label, style, grade.feedback)


def hint(text):
  _labelled("Hint", "bold yellow", text)


def explanation(decision):
  body = [Text(decision.reference_answer)]
  if decision.alternatives:
    body += [Text(""), Text("Alternatives", style="bold")]
    body += [Text(f"  • {a}") for a in decision.alternatives]
  console.print(Panel(Group(*body), title=" Explanation ", title_align="left", border_style="dim", padding=(0, 2), width=_width()))


def stopped():
  console.print()
  note("Stopping here. Progress saved.")


# ── end of session ────────────────────────────────────────────────────────

def end_card(tally, ownership_before, ownership_after, left, to_revisit, record_path):
  counts = Table.grid(padding=(0, 3))
  cells = [
    Text.assemble((str(tally["owned"]), "bold green"), " owned"),
    Text.assemble((str(tally["partial"]), "bold yellow"), " partial"),
    Text.assemble((str(tally["revisit"]), "bold red"), " to revisit"),
  ]
  if tally["skipped"]:
    cells.append(Text.assemble((str(tally["skipped"]), "bold"), " skipped"))
  counts.add_row(*cells)

  owned, total = ownership_after
  before_pct = _pct(*ownership_before)
  after_pct = _pct(owned, total)
  change = f"{before_pct}% → {after_pct}%" if after_pct != before_pct else f"{after_pct}%"

  meter = Table.grid(padding=(0, 2))
  meter.add_row(
    Text("Repo ownership", style="bold"),
    ProgressBar(total=100, completed=after_pct, width=24, complete_style="green", finished_style="green"),
    Text(f"{change}  ({owned}/{total} decisions)", style="dim"),
  )

  lines = [counts, Text(""), meter, Text("")]
  if left:
    lines.append(Text.assemble(("Next  ", "bold"), (f"mentor review --more", "cyan"), (f"  ({left} decision{'s' if left != 1 else ''} left)", "dim")))
  if to_revisit:
    lines.append(Text.assemble(("Retry  ", "bold"), ("mentor review --revisit", "cyan"), (f"  ({to_revisit} not owned yet)", "dim")))
  lines.append(Text.assemble(("Record  ", "bold"), (str(record_path), "dim")))

  console.print()
  console.print(Panel(Group(*lines), title=" Session complete ", title_align="left", border_style="green", padding=(1, 2), width=_width()))


def _pct(owned, total):
  return round(100 * owned / total) if total else 0
