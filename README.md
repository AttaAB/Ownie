# Do I Actually Understand My Own Code? | A CLI that quizzes you on the design decisions your AI made for you

## Inspiration (...I couldn't explain my own code)

I build a lot with AI coding assistants. I describe a feature, the AI writes
it, the tests pass, I ship it. Life is good.

Then someone asks *"why does this use SQLite?"* or *"what happens if two
requests hit this at the same time?"*... and I realise I have no idea.
Because I didn't make that decision. The AI did. Quietly. Along with about
forty others.

That's fine right up until you have to explain the code in a code review,
debug it at 2am during an incident, or defend it in an interview.

So instead of just hoping nobody asks, I built a tool to answer the
question once and for all: **do I actually understand the code I'm
shipping... or did I just press Enter a lot?**

## What this project does

`mentor review` reads the code in your repo (by default, whatever changed
since your last review) and:

1. **Finds the design decisions** the AI made for you: storage choices,
   concurrency assumptions, error handling, security safeguards, and so on
2. **Asks you about the most important ones**, as concrete scenarios
   ("two people claim the same alias at the same moment, what happens?")
3. **Grades your plain-English answer**: owned / partial / missing
4. **Keeps a record** of what you understand, plus an ownership score for
   the repo

It never changes your code. It just checks that *you* get it.

You're kept company by **Ownie**, a little pixel robot who waves hello,
thinks while the model works, and cheers when you own a decision. (It's
very supportive. Even when you're wrong.)

## How it works (the pipeline)

```text
scope → context → decisions (with hidden answer keys) → ranked → questions → grading → record
```

### 1) Finding decisions (answer key first)

For every decision, the model writes a hidden **answer key** *before* it
writes the question:

- **chosen**: what the code actually does
- **alternatives**: what it could have done instead
- **consequences**: what that choice means in practice
- **evidence**: the exact `file:line` that proves it

Why answer key first? Because a question without an answer key is just
vibes. With one, the question stays grounded and your answer can actually
be graded.

Then a plain, non-AI check throws out any decision whose `file:line`
evidence doesn't point at real code it was shown. (It has caught 0 so
far, but it's cheap insurance against the model making things up.)

### 2) Ranking (what you'd most likely get asked)

You only get asked 3 questions at a time, so order matters a lot.
Decisions are ranked by: **would you be embarrassed not to be able to
explain this in a code review?** In practice:

- things central to what the code is *for* come first
- **except** severe security risks (anyone can read other people's data,
  run code on the server, injection), which always jump the queue

### 3) Grading (owned / partial / missing)

- **owned**: you explained what happens *and why*
- **partial**: you're right, but it's surface-level
- **missing**: wrong, or off-topic

The grader sees the answer key *and* the actual code, so if you know
something the answer key missed, you still get credit. It's also built to
be strict in one direction: it would rather call a good answer "partial"
than call a wrong answer "owned". Giving you false confidence is the worst
thing this tool could do.

### 4) The record

Everything goes into `.mentor/DECISIONS.md`, with a status per decision:
✓ owned, ◐ partial, ○ to revisit, ↻ code changed.

- If the code behind a decision you owned changes later, it gets marked
  "code changed" and you're asked about it again
- If a later review finds the same decision, it keeps its identity, so
  nothing gets listed twice

## How I know it works (the math)

I didn't want to just *feel* like the questions were good, so I built an
eval and measured every change.

### The benchmark

- 4 small projects (2 Python, 2 TypeScript). 3 of them were vibe-coded by
  fresh AI agents from a one-paragraph prompt, with zero design steering
  (the 4th I built by hand)
- Each project also got one follow-up change, written the same way
- I hand-labelled **51 design decisions** across them, and marked which
  ones are **must-know**
- For the follow-up changes, I set the priorities **blind**: the AI's
  suggestions were hidden and the order shuffled. (I disagreed with the AI
  on 10 of 19. Which is kind of the whole point.)

### Metric definitions

Must@3 (are the 3 questions I get asked the ones that matter?):
`Must@3 = (must-know decisions in the top 3) / min(3, total must-know decisions)`

Must(any) (did it find the must-know ones at all?):
`Must(any) = (must-know decisions found at any rank) / (total must-know decisions)`

Recall (did it find the decisions I labelled?):
`Recall = (labelled decisions found) / (total labelled decisions)`

Precision (are the decisions it reports real?):
`Precision = (real decisions reported) / (total decisions reported)`

Grader agreement (does the grader grade answers the way I would?):
every label comes with a sample good, partial and wrong answer, and
`Grader = (sample answers graded as labelled) / (total sample answers)`

Every config runs 3 times per project (the model is random-ish), and a
change is only kept if it helps without breaking something else.

### What the experiments taught me

| Change | Result |
|---|---|
| Also ask about *safeguards*, not just risks | recall 52% → 74% |
| Aim each question at the decision's central consequence | must-know found 63% → 90%, recall → 80% |
| Grader rule: never "owned" for a wrong answer | false "owned" 7 → 0 |
| A separate AI call just to re-rank decisions | +3 points, basically noise. **Rejected** |
| Rank by "central to the code" instead of "security first" | Must@3 72% → 92% |
| Severe security risks always first (my call) | trial app: "no auth" asked first; Must@3 92% → 81% |
| Grader sees the actual code | fixed a real bug where a *correct* answer got marked wrong |
| One scenario per question | Must@3 81% → 89%, grader 74% → 78%, questions 36 → 30 words |

A few things that surprised me:

- **The ranking bug was one sentence.** I'd told the model to "weigh
  security above other categories", so minor security details kept
  outranking the stuff that actually mattered. Adding a whole second AI
  call to re-rank didn't fix it (it had the same bias). Rewriting the one
  sentence did.
- **The AI judge was useless.** I used another model call to score
  question quality, then rated 20 questions myself to check it. It agreed
  with me 31% of the time, where a coin flip gets 50%. So now I rate
  question quality by hand.
- **A whole planned feature turned out to be unnecessary.** I was going to
  build fancy retrieval (repo maps, cross-file references, an agent with
  search tools). Then I measured: looking only at the diff, it already
  finds 94-96% of the must-know decisions. So I didn't build it.
- **Real use found what the benchmark couldn't.** The first time I used it
  on a fresh app, it marked one of my *correct* answers as wrong, because
  I knew something the answer key didn't. The benchmark never caught this
  because its sample answers never go beyond the answer key. Fix: let the
  grader read the code.

### Current results

| Suite | Must@3 | Must(any) | Recall | Precision |
|---|---|---|---|---|
| Whole project (32 labels) | 89% | 92% | 79% | 100% |
| One change, diff only (19 labels) | 62% | 96% | 94% | 100% |

The grader agrees with my labels 78% of the time. Of 258 wrong or
surface-level sample answers, it graded 1 as "owned": a borderline answer
that's only wrong outside the question's scenario, and that got marked
partial or missing in 9 out of 9 re-grades.

Note on the 62%: some of Must@3 is just taste. A model and a human can
reasonably disagree about which decision matters *most*, and I'd rather
not tune the prompt to match my personal opinions with only one labeller
(me).

## Setup (if you'd like to try it)

### 1) Install it

```bash
pipx install git+https://github.com/AttaAB/engineer-mentor
```

No pipx? `brew install pipx` (macOS) or `python3 -m pip install --user pipx`.
Plain pip works too: `pip install git+https://github.com/AttaAB/engineer-mentor`.

### 2) Add your OpenAI key

```bash
mkdir -p ~/.config/mentor && echo "OPENAI_API_KEY=sk-..." > ~/.config/mentor/.env
```

(Or set the `OPENAI_API_KEY` environment variable. It never reads the
`.env` of the repo you're reviewing.)

> **Privacy:** the code you review gets sent to the OpenAI API to find
> decisions and grade answers. Don't run it on code you can't share. Put
> paths you want skipped in a `.mentorignore` file (one per line, e.g.
> `vendor/`).

### 3) Run it in any git repo

```bash
cd my-vibe-coded-app
mentor review
```

During a review, type your answer in plain English and press Enter, or:
`h` hint · `e` explain (and move on) · `s` skip · `q` quit (progress is
saved). You get 3 tries per question.

### All the commands

```bash
mentor review                  # what's new since your last review
mentor review --uncommitted    # only what's not committed yet
mentor review --since 3        # the last 3 commits (or a date: "3 days ago", or a commit hash)
mentor review --base develop   # on a branch, compare against develop
mentor review --all            # the whole repo
mentor review --more           # decisions it found but didn't ask yet
mentor review --revisit        # retry the ones you didn't own
mentor review -n 5             # 5 questions instead of 3
mentor review -v               # show each step as it runs
mentor review --plain          # no Ownie, no animation (or MENTOR_PLAIN=1)
mentor status                  # your ownership score and what's waiting (no API calls)
```

On a feature branch, `mentor review` looks at changes since the branch
split from `main`. On `main`, it looks at everything since your last
review (the first run asks what to look at). Uncommitted changes are
always included.

### 4) Use it inside Claude Code (optional)

Install the `/mentor` command once:

```bash
mkdir -p ~/.claude/commands
curl -fsSL -o ~/.claude/commands/mentor.md \
  https://raw.githubusercontent.com/AttaAB/engineer-mentor/main/integrations/claude-code/mentor.md
```

Then, right after Claude writes some code, type `/mentor --uncommitted` in
the Claude Code chat. Claude asks you the questions and passes your answers
to `mentor` for grading. It's told not to hint, answer or grade for you
(no cheating). It uses the same `.mentor/` record as the terminal version.

Under the hood these are plain JSON commands, so any tool can drive a review:

```bash
mentor ask [--uncommitted | --all | --more | --revisit ...] [-n N]
mentor answer ID "your answer"      # or the answer on stdin
mentor hint ID · mentor explain ID · mentor skip ID
```

## Project outputs

You'll end up with:

- `.mentor/DECISIONS.md`: every decision, the alternatives and trade-offs,
  your explanation, and its status
- `.mentor/state.json`: review state (last reviewed commit, statuses,
  decisions not asked yet)

Commit `.mentor/` if you want the record in your repo; ignore it if not.

Want to see a full session first? There's a real one in
[docs/demo.md](docs/demo.md). The longer story of how it was built and
measured is in [docs/WRITEUP.md](docs/WRITEUP.md), and the code layout is
in [ARCHITECTURE.md](ARCHITECTURE.md).

## Notes / limitations

- This is a learning project, not a perfect truth machine.
- **Small benchmark:** 51 labels and one human labeller (me). Results
  bounce around ±15-25 points between runs, so small improvements are hard
  to tell apart from noise.
- **Small projects:** each benchmark project fits in one model context.
  Really big changes get cut off (it warns you when that happens).
- **The grader is a bit harsh.** Good answers often get "partial",
  especially when a question has two parts. That's on purpose (better
  harsh than falsely confident), but it can be annoying.
- It costs a few OpenAI calls per review (one to find decisions, one per
  answer you submit).

## Future improvements (if I don't get roasted by my own tool and quit)

- Try it on way more real repos (honestly the most useful bugs came from
  real use, not the benchmark)
- Get more people to label the benchmark, so it measures more than just
  *my* opinion
- Make questions consistently single-part (still 25-50% have a second part)
- Smarter handling of really big changes
- A proper GIF of Ownie in action for this README

## Running the eval yourself

```bash
python -m venv .venv
.venv/bin/pip install -e ".[eval]"
echo "OPENAI_API_KEY=sk-..." > .env

python -m evals.run                         # whole-project suite, 3 runs → evals/results/
python -m evals.run --suite change          # review only each project's follow-up change
python -m evals.run --config my-change      # name a variant
python -m evals.compare baseline my-change  # side-by-side with deltas
python -m evals.grader_replay my-change     # re-grade stored answer keys (grader changes)
python -m evals.benchmark --check           # every label's path:line exists
python -m evals.review_labels               # review change-suite labels (you're the ground truth)
python -m evals.rate                        # hand-rate question quality
```

Set `MENTOR_MODEL` to change the model, or `MENTOR_JUDGE_MODEL` to judge
with a different one.

## Feedback

If you have suggestions to make the questions sharper, the grading fairer,
or the code cleaner, please let me know! Still learning, and extremely
willing to be told what I got wrong. (Ironically, that's the whole point
of this tool.)
