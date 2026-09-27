# Decision Benchmark

Small vibe-coded projects with hand-verified labels of the design
decisions they contain. `python -m evals.run` measures how well `mentor`
finds those decisions, how good its questions are, and how accurately it
grades answers.

```text
benchmark/
  <project>/
    repo/          the project's source (plain files; no .git, no node_modules)
    labels.yaml    ground-truth decisions + sample answers (see link-shortener/)
    changes/
      <name>/
        change.patch   a follow-up change to repo/ (git diff, new files included)
        labels.yaml    decisions made *in that change*; locations cite the
                       code after the change, on lines the change touched
```

Two suites: `python -m evals.run` reviews each whole repo;
`python -m evals.run --suite change` commits the repo, applies the patch
as a second commit, and reviews only that commit — the way `mentor review`
is used after someone (or an AI) makes a change.

| Project | Language | Built by | Labels |
|---|---|---|---|
| link-shortener | Python / FastAPI | hand-made, 3 planted decisions | 7 (3 must-find) |
| notes-app | TypeScript / Next.js | fresh agent, prompt below | 8 (3 must-find) |
| sync-cli | Python | fresh agent, prompt below | 8 (4 must-find) |
| webhook-api | TypeScript / Express | fresh agent, prompt below | 9 (4 must-find) |

| Change | Feature request (the agent's only instructions) | Labels |
|---|---|---|
| link-shortener/custom-alias-expiry | custom alias + optional expiry date | 5 (2 must-find) |
| notes-app/image-attachments | attach images; show them on the shared page | 5 (2 must-find) |
| sync-cli/multi-folder-sync | several folders from a config file, in parallel | 5 (2 must-find) |
| webhook-api/refunds | refund webhook → update status, email the customer | 4 (2 must-find) |

Labels are AI-drafted and fact-checked against the code (every
`path:line` validated); **priorities are the developer's call** — a
project counts as verified once its `verified: true` is set.

## How to build a project

The three generated projects were built by fresh Claude Code agents given
*only* the prompt below — no knowledge of mentor, the benchmark, or the
labels, and no design steering — which is equivalent to a user pasting
the prompt into a new session. To add a project by hand instead:

The point is to capture how AI assistants make decisions *when nobody is
steering the design* — so build these the way a vibe coder would.

1. Make an empty folder **outside this repo** and open a fresh Claude Code
   session in it:
   ```bash
   mkdir -p ~/Desktop/Developer/mentor-benchmark/notes-app
   cd ~/Desktop/Developer/mentor-benchmark/notes-app && git init && claude
   ```
2. Paste the project's prompt below. Accept its choices; only intervene
   when something doesn't run. Don't ask for "best practices", don't
   review the design, don't read `labels.yaml` for other projects first.
3. Stop when the feature list works (roughly 300–1,000 lines). Commit.
4. Copy the source into the benchmark (skipping git, deps, build output):
   ```bash
   rsync -a --exclude .git --exclude node_modules --exclude .next \
     --exclude dist --exclude __pycache__ --exclude .venv --exclude '*.db' \
     ~/Desktop/Developer/mentor-benchmark/notes-app/ \
     ~/Desktop/Developer/engineering-mentor/benchmark/notes-app/repo/
   ```
5. Tell Claude (in the engineering-mentor session) the project is in; it
   drafts `labels.yaml`, and you review it (below).

## How to add a change

Same rule — no steering. Copy the project's `repo/` into a fresh git repo
outside this one (one "base" commit), give a fresh agent only a one-line
feature request ending "Keep it simple and get it working.", then save the
result with new files included:

```bash
git add -A && git diff --cached --binary > benchmark/<project>/changes/<name>/change.patch
```

Draft `labels.yaml` next to it (the request goes in its header), then run
`python -m evals.benchmark --check`.

## Prompts

### notes-app (TypeScript / Next.js)

> Build a small notes app with Next.js (App Router) and TypeScript. Users
> can sign up and log in with email and password, then create, edit,
> delete, and search their own notes. Notes support tags and can be
> shared via a public read-only link. Store data in SQLite. Keep it simple
> and get it working end to end.

### sync-cli (Python)

> Write a Python command-line tool that keeps a local folder in sync with
> a remote HTTP file server. It should list remote files from a JSON
> endpoint, download new or changed files, delete local files that were
> removed remotely, and run on a schedule every few minutes. Show
> progress, and handle the network being flaky. Include a small fake
> server so it can be tried locally.

### webhook-api (TypeScript / Express)

> Build an Express + TypeScript service that receives payment webhooks
> from a provider like Stripe, records each payment in Postgres (or
> SQLite if easier), and sends the customer a confirmation email. Also
> add an endpoint to list a customer's payments. Include a script that
> sends a sample webhook so it can be tested locally.

## Reviewing labels (the part only you can do)

You are the ground truth — if the AI both labels and gets graded, the
benchmark just measures its own opinions. For each decision in
`labels.yaml`, check:

- **Real?** Is it actually a decision in this code, at that location?
- **Priority right?** `must-find` = you'd be embarrassed not to be able to
  explain it in a code review. Everything else is `nice-to-find`.
- **Missing?** Anything important the AI didn't list? Add it.
- **Answers realistic?** `good` / `partial` / `wrong` should sound like
  things a real developer would say.

Then set `verified: true` at the top.

Change cases are reviewed with `python -m evals.review_labels`: it shows
each label's code (changed lines highlighted), claim and sample answers —
but hides the suggested priority and shuffles the order, so your call
isn't anchored on the AI's. Press `m`/`n` for must-find/nice-to-find, `x`
if it isn't a real decision, `c` to note a wrong claim; it resumes where
you stopped. Fully reviewed changes with no notes are marked verified
automatically; notes are resolved by Claude and re-checked by you. A
change's must-finds are what you'd expect the author of *that change* to
explain in its code review. Unverified projects still run but
are flagged in results.
