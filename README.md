# Engineering Mentor

**Own the design decisions in code you didn't write.**

AI coding assistants make dozens of design decisions for you — a storage
choice, a concurrency assumption, an error-handling policy — and you're
still the one who has to explain them in code review, an incident, or an
interview. `mentor` finds those implicit decisions in your changes, asks
you Socratic questions about them, grades your answers, and keeps a
decision record of what you understand.

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e .
echo "OPENAI_API_KEY=sk-..." > .env
```

## Usage

Run inside any git repository:

```bash
mentor review                  # smart default (see below)
mentor review --uncommitted    # only what's not committed yet
mentor review --since <ref>    # from a commit, or a date like "3 days ago"
mentor review --base develop   # on a branch, compare against develop
mentor review --all            # the whole repo
mentor review --more           # continue with leftover decisions
mentor review --revisit        # retry decisions you haven't owned yet
mentor status                  # ownership score and what's waiting (no API calls)
mentor review -v               # show each pipeline step
```

**Smart default:** on a feature branch, reviews changes since the branch
split from `main`. On `main`, reviews everything since your last review
(the first run asks what to look at). Uncommitted changes are always
included.

To skip paths (generated code, vendored libraries), list globs in a
`.mentorignore` file at the repo root, one per line — e.g. `vendor/`.

During a review, type an answer, or `h` (hint), `e` (explain), `s` (skip),
`q` (quit — progress is saved).

## Output

- `.mentor/DECISIONS.md` — each decision, the alternatives and trade-offs,
  your explanation, and whether you own it.
- `.mentor/state.json` — review state (last reviewed commit, statuses,
  leftover decisions).

## How it works

```text
scope → context → decisions (with hidden answer keys) → questions → grading → record
```

Each decision's answer key — what was chosen, alternatives, consequences,
and `file:line` evidence — is built before the question is written, which
keeps questions grounded and makes answers gradable.

Set `MENTOR_MODEL` to override the default model.

## Evaluation

`benchmark/` holds small projects with hand-verified labels of the design
decisions they contain (see `benchmark/README.md`). The eval runs the same
pipeline users get and scores it:

```bash
.venv/bin/pip install -e ".[eval]"
python -m evals.run                         # all projects × 3 runs → evals/results/
python -m evals.run --config my-change      # name a variant
python -m evals.run --suite change          # review only each project's follow-up change
python -m evals.compare baseline my-change  # side-by-side with deltas
python -m evals.benchmark --check           # every label's path:line exists
python -m evals.review_labels               # review change-suite labels (you're the ground truth)
```

| Metric | Meaning |
|---|---|
| Must@3 | share of must-find decisions that made the top 3 questions |
| Recall | share of labelled decisions found at all |
| Precision | share of kept decisions that are real (label match or judge-confirmed) |
| Quality / No-leak | LLM-judge scores (1–5) for question quality and not giving the answer away |
| Grader | share of sample answers the grader grades as labelled |
| Dropped | share of decisions removed by the citation check |

Set `MENTOR_JUDGE_MODEL` to judge with a different model than the mentor.
