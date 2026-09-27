# Engineering Mentor

**Own the design decisions in code you didn't write.**

AI coding assistants make dozens of design decisions for you — a storage
choice, a concurrency assumption, an error-handling policy — and you're
still the one who has to explain them in code review, an incident, or an
interview. `mentor` finds those implicit decisions in your changes, asks
you scenario questions about them, grades your answers, and keeps a
decision record of what you understand.

It never changes your code. It checks that *you* understand it.

## Install

```bash
pipx install git+https://github.com/AttaAB/engineer-mentor
mkdir -p ~/.config/mentor && echo "OPENAI_API_KEY=sk-..." > ~/.config/mentor/.env
```

No pipx? `brew install pipx` (macOS) or `python3 -m pip install --user pipx`.
Plain pip works too: `pip install git+https://github.com/AttaAB/engineer-mentor`.
The key can also come from the `OPENAI_API_KEY` environment variable;
the reviewed repo's own `.env` is never read.

> **Privacy:** the code under review is sent to the OpenAI API to find
> decisions and grade answers. Don't run it on code you can't share with
> OpenAI. Use `.mentorignore` to leave paths out.

## Quick start

```bash
cd my-vibe-coded-app
mentor review
```

A session looks like this (abridged, from a real run on a small Flask API):

```text
╭─ security · splitter/app.py:139-253 ─────────────────────────────────────╮
│  Q  Two people can reach the running server, and one of them knows or    │
│     guesses another group's numeric ID. Walk through what that person    │
│     can do using the group, member, expense, and balance endpoints.      │
╰──────────────────────────────────────────────────────────── 1/3 ─────────╯
› there's no authentication anywhere, so anyone who can reach the server
  can read and write every group. They don't even need to guess an ID.

✓ owned — You correctly identify that reachability alone gives full access.
  In particular, GET /groups lists every group's ID, so guessing is
  unnecessary.
```

At the end you get an ownership score for the repo and a record in
`.mentor/DECISIONS.md`. The next `mentor review` only covers what's new.

A full recorded session is in [docs/demo.md](docs/demo.md). How it was
built and measured, and what the experiments taught, is in
[docs/WRITEUP.md](docs/WRITEUP.md).

## Use it inside Claude Code

Install the `/mentor` command once:

```bash
mkdir -p ~/.claude/commands
curl -fsSL -o ~/.claude/commands/mentor.md \
  https://raw.githubusercontent.com/AttaAB/engineer-mentor/main/integrations/claude-code/mentor.md
```

Then, right after Claude writes code, type `/mentor --uncommitted` (or
`/mentor`, `/mentor --more`, `/mentor --revisit`). Claude shows each
question and passes your answers to `mentor answer` for grading — it's
told not to hint or answer for you. It uses the same `.mentor/` record as
the terminal version, via JSON commands you can use from any tool:

```bash
mentor ask [--uncommitted | --all | --more | --revisit ...] [-n N]
mentor answer ID "your answer"      # or the answer on stdin
mentor hint ID · mentor explain ID · mentor skip ID
```

## Commands

```bash
mentor review                  # smart default (see below)
mentor review --uncommitted    # only what's not committed yet
mentor review --since <ref>    # from a commit, or a date like "3 days ago"
mentor review --base develop   # on a branch, compare against develop
mentor review --all            # the whole repo
mentor review --more           # continue with decisions not asked yet
mentor review --revisit        # retry decisions you haven't owned yet
mentor review -n 5             # ask 5 questions instead of 3
mentor review -v               # show each pipeline step
mentor status                  # ownership score and what's waiting (no API calls)
```

**Smart default:** on a feature branch, reviews changes since the branch
split from `main`. On `main`, reviews everything since your last review
(the first run asks what to look at). Uncommitted changes are always
included.

**During a review:** type your answer in plain English and press Enter,
or `h` (hint), `e` (explain and move on), `s` (skip), `q` (quit — progress
is saved). Each question allows three attempts.

**Grades:** *owned* — you explained what happens and why; *partial* —
correct but surface-level; *missing* — wrong or off-topic. The grader
checks your claims against the code, and it would rather say "partial"
to a good answer than "owned" to a wrong one.

**Skipping paths:** list globs in a `.mentorignore` file at the repo root,
one per line — e.g. `vendor/`.

## What it keeps

- `.mentor/DECISIONS.md` — each decision, the alternatives and trade-offs,
  your explanation, and its status: ✓ owned, ◐ partial, ○ to revisit,
  ↻ code changed.
- `.mentor/state.json` — review state (last reviewed commit, statuses,
  decisions not asked yet).

If the code behind a decision you owned changes later, it's marked
"code changed" and asked about again. A decision found again in a later
review keeps its identity, so nothing is listed twice.

Commit `.mentor/` if you want the record in the repo; ignore it if not.

## How it works

```text
scope → context → decisions (with hidden answer keys) → ranked → questions → grading → record
```

Each decision's answer key — what was chosen, alternatives, consequences,
and `file:line` evidence — is built before the question is written, which
keeps questions grounded and makes answers gradable. Decisions whose
citations don't point at real code are dropped. Decisions are ranked by
how central they are to what the code does, with severe security risks
first. See `ARCHITECTURE.md` for the code layout.

Set `MENTOR_MODEL` to override the default model.

## Evaluation

Every prompt change is measured before it's kept. `benchmark/` holds
four small projects (two Python, two TypeScript) built by AI agents with
no design steering, plus one follow-up change each; a human labelled the
design decisions in them and which ones matter most (see
`benchmark/README.md`). The eval runs the same pipeline users get.

Current results (3 runs per project):

| Suite | Must@3 | Must(any) | Recall | Precision |
|---|---|---|---|---|
| Whole project (32 labels) | 81% | 88% | 80% | 100% |
| One change, diff only (19 labels) | 63% | 94% | 94% | 100% |

The grader agrees with labelled sample answers 71–74% of the time, and
never graded a wrong or surface-level answer "owned" (0 of 258 in the
latest replays).

```bash
.venv/bin/pip install -e ".[eval]"
python -m evals.run                         # whole-project suite, 3 runs → evals/results/
python -m evals.run --suite change          # review only each project's follow-up change
python -m evals.run --config my-change      # name a variant
python -m evals.compare baseline my-change  # side-by-side with deltas
python -m evals.grader_replay my-change     # re-grade stored answer keys (grader changes)
python -m evals.benchmark --check           # every label's path:line exists
python -m evals.review_labels               # review change-suite labels (you're the ground truth)
python -m evals.rate                        # hand-rate question quality
```

| Metric | Meaning |
|---|---|
| Must@3 | share of the 3 questions asked that are must-know decisions |
| Must(any) | share of must-know decisions found at any rank |
| Recall | share of labelled decisions found at all |
| Precision | share of reported decisions that are real |
| Grader | share of sample answers graded as labelled |
| Quality / No-leak | LLM-judge scores (1–5), reference only — they didn't track human ratings |

Set `MENTOR_JUDGE_MODEL` to judge with a different model than the mentor.

**For development** (editable install, plus the eval tools):

```bash
python -m venv .venv
.venv/bin/pip install -e ".[eval]"
echo "OPENAI_API_KEY=sk-..." > .env
```
