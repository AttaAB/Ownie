# Architecture

`mentor review` reads code you didn't write, finds the design decisions in
it, asks you about them, grades your answers, and records what you
understand. The codebase has two halves: the **product** (`mentor/`) and
the **measurement** that tells us whether the product is any good
(`evals/` + `benchmark/`).

## How a review flows

```text
mentor review
  cli.py ── scope.py ─────── which code? (git range, or --all)          uses git.py
        └─ pipeline.py ──── analyze(scope):
              context.py      code → line-numbered text for the model
              llm.py          extract decisions (each with a hidden answer key)
              verify.py       drop decisions whose file:line citations don't exist
        └─ session.py ───── ask → answer → grade (llm.py) → hint / explain
        └─ record.py ────── .mentor/state.json → .mentor/DECISIONS.md
        ui.py renders everything; models.py defines the shared data shapes
```

## Product — `mentor/`

| File | Job |
|---|---|
| `cli.py` | The `mentor` command: parses flags, runs the steps above in order. |
| `scope.py` | Decides which code to review: branch vs main, since last review, `--since`, `--uncommitted`, `--all`; applies `.mentorignore`. |
| `git.py` | Thin wrapper around the `git` command line. |
| `pipeline.py` | `analyze(scope)`: the non-interactive core. **The CLI and the evals both call this**, so what we measure is what users get. |
| `context.py` | Turns the scope into text for the model, with a line number on every line so it can cite `file:line`. |
| `llm.py` | The two model calls: `extract_decisions` and `grade_answer`, plus their prompts. |
| `verify.py` | Deterministic check: a decision survives only if one of its citations points at code the model was actually shown. |
| `models.py` | `Decision` (the answer key + the question) and `Grade`. |
| `session.py` | The interactive question loop. |
| `record.py` | Saves review state and regenerates `DECISIONS.md` from it. |
| `ui.py` | Everything the user sees (rich panels, code snippets, end card). |

## Measurement — `benchmark/` + `evals/`

| Path | Job |
|---|---|
| `benchmark/<project>/repo/` | A small project's source (2 Python, 2 TypeScript). |
| `benchmark/<project>/labels.yaml` | The answer key: decisions that should be found, their priority, and sample good/partial/wrong answers. Priorities are human-decided. |
| `evals/run.py` | Runs `analyze()` on every project (several runs each, in parallel) and scores it. |
| `evals/judge.py` | AI judge: matches predictions to labels and rates question quality. |
| `evals/benchmark.py` | Loads projects and copies each into a throwaway git repo. |
| `evals/compare.py` | Before/after table between two eval runs. |
| `evals/grader_replay.py` | Re-tests only the grader, on saved answer keys (like-for-like). |
| `evals/rate.py` | A human rates questions, to check whether the AI judge can be trusted. |
| `evals/results/` | Every eval's scores, one JSON line per project run. |

Metrics: **Must@3** (are the 3 questions asked the must-know decisions?),
**Must(any)** / **Recall** (were decisions found at all?), **Precision**
(are they real?), **Grader** (does grading match the labelled answers?),
plus AI-judge quality scores, which are **reference only**: calibrated
against 20 human ratings they did no better than chance, so question
quality is checked with human ratings (`evals/rate.py`) instead.

## Design decisions (and why)

- **Answer key before question.** Every decision is extracted with what
  was chosen, alternatives, consequences, and evidence *before* the
  question is written — keeps questions grounded and makes answers
  gradable.
- **Decisions include safeguards, not just risks.** Owning code means
  knowing what you'd break by removing a correct safeguard. Adding this
  raised recall from 52% to 74%.
- **Local git, not the GitHub API.** Works before a PR exists, on any
  branch, with no rate limits. Default scope is "since last review" so
  it works for people who commit straight to main.
- **One shared pipeline.** The eval can't drift from the product.
- **The grader never gives false confidence.** It would rather mark a
  good answer "partial" than mark a wrong one "owned".
- **Evals are the judge of every change.** Keep a change only if the
  numbers improve.

## Rules for changing things

1. Measure every change to prompts or retrieval: `python -m evals.run
   --config <name>` then `python -m evals.compare <before> <name>`.
2. Never put benchmark content (label wording, project-specific examples)
   into prompts — that turns the eval into a memory test.
3. The benchmark's `labels.yaml` priorities are human decisions; don't
   edit them to make numbers go up.
