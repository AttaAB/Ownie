"""Ownie, mentor's pixel-robot mascot.

Ownie is drawn on a small pixel grid and rendered with half-block
characters: each terminal cell shows two stacked pixels (upper half in the
foreground colour of "▀", lower half in its background), which is what makes
it look like pixel art rather than ASCII.

Purely decorative: ui.py decides when Ownie appears, and `enabled()` turns
it off for pipes, CI, `--plain`, or MENTOR_PLAIN=1.
"""

import os
import random
import threading
import time
from contextlib import contextmanager

from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

NAME = "Ownie"

# One letter per pixel; "." is transparent. Change the body colour here.
PALETTE = {
  "B": "#23b5a3",  # body (teal)
  "D": "#13786c",  # arms and feet (darker teal)
  "E": "#0c1d1b",  # eyes
  "M": "#0c1d1b",  # mouth
  "A": "#ffd166",  # antenna light, on
  "a": "#6b5a2c",  # antenna light, off
  "S": "#13786c",  # antenna stem
  "H": "#ff8fab",  # heart (cheering)
}

# 13 x 10 pixels → 13 x 5 cells. Rows: antenna, head, eyes, mouth, feet.
_BASE = [
  "......A......",
  "......S......",
  "..BBBBBBBBB..",
  "..BBBBBBBBB..",
  "..BEEBBBEEB..",
  "..BEEBBBEEB..",
  "..BBBBBBBBB..",
  "..BBBMMMBBB..",
  "...BBBBBBB...",
  "...DD...DD...",
]


def _with(rows, changes):
  """A copy of `rows` with {(row, col): letter} applied."""
  grid = [list(r) for r in rows]
  for (r, c), letter in changes.items():
    grid[r][c] = letter
  return ["".join(r) for r in grid]


_ARMS_DOWN = {(5, 1): "D", (6, 0): "D", (5, 11): "D", (6, 12): "D"}
_RIGHT_UP = {(5, 1): "D", (6, 0): "D", (4, 11): "D", (3, 12): "D"}
_BOTH_UP = {(4, 1): "D", (3, 0): "D", (4, 11): "D", (3, 12): "D"}
_BLINK = {(4, 3): "B", (4, 4): "B", (4, 8): "B", (4, 9): "B"}
# Happy face: eyes squint (lower eye row closes) and the mouth corners turn up.
_SMILE = {(5, 3): "B", (5, 4): "B", (5, 8): "B", (5, 9): "B", (6, 4): "M", (6, 8): "M"}
_LOOK_UP = {(5, 3): "B", (5, 4): "B", (5, 8): "B", (5, 9): "B", (3, 3): "E", (3, 4): "E", (3, 8): "E", (3, 9): "E",
            (4, 3): "E", (4, 4): "E", (4, 8): "E", (4, 9): "E"}
_ANTENNA_OFF = {(0, 6): "a"}
_HEART = {(0, 6): "H"}

POSES = {
  "idle": _with(_BASE, _ARMS_DOWN),
  "blink": _with(_BASE, {**_ARMS_DOWN, **_BLINK}),
  "wave": _with(_BASE, {**_RIGHT_UP, **_SMILE}),
  "happy": _with(_BASE, {**_ARMS_DOWN, **_SMILE}),
  "cheer": _with(_BASE, {**_BOTH_UP, **_SMILE, **_HEART}),
  "think": _with(_BASE, {**_ARMS_DOWN, **_LOOK_UP}),
  "think_off": _with(_BASE, {**_ARMS_DOWN, **_LOOK_UP, **_ANTENNA_OFF}),
}

# Animations: (pose, seconds) frames.
HELLO = [("idle", 0.25), ("wave", 0.3), ("idle", 0.2), ("wave", 0.3), ("blink", 0.12), ("happy", 0)]
THINKING = [("think", 0.45), ("think_off", 0.45), ("think", 0.45), ("blink", 0.15)]


def enabled(console):
  return console.is_terminal and not os.environ.get("MENTOR_PLAIN")


def sprite(pose="idle"):
  """The pose as a rich Text, two pixel rows per line."""
  rows = POSES[pose]
  text = Text()
  for top, bottom in zip(rows[0::2], rows[1::2]):
    for t, b in zip(top, bottom):
      text.append(*_cell(PALETTE.get(t), PALETTE.get(b)))
    text.append("\n")
  text.rstrip()
  return text


def _cell(top, bottom):
  if top and bottom:
    return ("▀", Style(color=top, bgcolor=bottom)) if top != bottom else ("█", Style(color=top))
  if top:
    return ("▀", Style(color=top))
  if bottom:
    return ("▄", Style(color=bottom))
  return (" ", Style())


def with_bubble(pose, message, width=None):
  """Ownie next to a speech bubble."""
  bubble = Panel(Text(message), box=box.ROUNDED, border_style=PALETTE["B"], padding=(0, 1),
                 title=Text(NAME, style=f"bold {PALETTE['B']}"), title_align="left", width=width)
  grid = _beside()
  grid.add_row(sprite(pose), bubble)
  return grid


def _beside():
  """Ownie on the left (never wrapped or squeezed), something else on the right."""
  grid = Table.grid(padding=(0, 2))
  grid.add_column(vertical="middle", no_wrap=True, min_width=13)
  grid.add_column(vertical="middle")
  return grid


def say(console, pose, message, width=None):
  console.print(with_bubble(pose, message, width))


def hello(console, message, width=None):
  """Wave and blink, then stay on screen with the message."""
  with Live(with_bubble(HELLO[0][0], message, width), console=console, refresh_per_second=20) as live:
    for pose, seconds in HELLO:
      live.update(with_bubble(pose, message, width))
      time.sleep(seconds)


@contextmanager
def thinking(console, message):
  """Animated Ownie while something slow runs; disappears afterwards."""
  stop = threading.Event()
  start = time.monotonic()
  cycle = sum(seconds for _, seconds in THINKING)

  def frame():
    t = (time.monotonic() - start) % cycle
    for pose, seconds in THINKING:
      if t < seconds:
        break
      t -= seconds
    dots = "." * (1 + int(time.monotonic() - start) % 3)
    grid = _beside()
    grid.add_row(sprite(pose), Text(message.rstrip("…. ") + dots, style="dim"))
    return grid

  with Live(frame(), console=console, refresh_per_second=12, transient=True) as live:
    def animate():
      while not stop.wait(0.08):
        live.update(frame())
    thread = threading.Thread(target=animate, daemon=True)
    thread.start()
    try:
      yield
    finally:
      stop.set()
      thread.join()


# A little variety, so Ownie doesn't say the same thing every time.
_LINES = {
  "start": [
    "Let's see what you shipped!",
    "Ooh, new code. Let's find out what it decided for you.",
    "Beep boop. Time to own some decisions!",
  ],
  "cheer": [
    "You own all of it. Ship it with confidence!",
    "Perfect run! I'm doing a little robot dance.",
  ],
  "happy": [
    "Nice work. You own more of this code than when we started.",
    "Good session! Every decision you own is one less surprise later.",
  ],
  "encourage": [
    "No worries — now you know where to dig. Try `mentor review --revisit` later.",
    "That's what reviews are for. Read the explanations, then come back!",
  ],
}


def line(kind):
  return random.choice(_LINES[kind])
