# Engineering Mentor — write-up

## The problem

More and more code is written by AI assistants: someone describes a
feature, accepts what comes back, and ships it. The code works, but the
assistant made dozens of design decisions along the way — where data
lives, what happens when two requests race, what a failure does to the
user — and the person shipping it often can't explain them. That gap
shows up in code review, during incidents, and in interviews.

`mentor review` closes it. It finds the design decisions in code you
didn't write, asks you about them as concrete scenarios ("two people
claim the same alias at the same moment — what happens?"), grades your
plain-English answer, and keeps a record of what you own. It never
changes the code.

## How it works

1. **Scope.** Local git decides what to look at: changes since your last
   review by default, or a branch, `--since`, `--uncommitted`, `--all`.
2. **Decisions with hidden answer keys.** One model call reads the code
   and returns decisions. For each one, it builds the answer key *before*
   writing the question: what was chosen, the alternatives, the
   consequences, and `file:line` evidence. A deterministic check drops any
   decision whose citations don't point at code the model was shown.
3. **Ranking.** Decisions are ordered by how central they are to what the
   code is for, with severe security risks first.
4. **Questions and grading.** The top three are asked as scenarios. The
   grader sees the answer key *and* the cited code, and grades owned /
   partial / missing. It's built to never give false confidence.
5. **Record.** `.mentor/DECISIONS.md` and an ownership score. Later
   reviews reuse decision ids (no duplicates), and re-ask an owned
   decision if its code changes.

It runs in the terminal, or inside Claude Code via `/mentor`, using the
same pipeline and state.

## Measuring it

Strong questions need measurement, not vibes, so the project was built
around an eval from the start.

**Benchmark.** Four small projects (two Python, two TypeScript). Three
were vibe-coded by fresh AI agents from a one-paragraph product prompt,
with no knowledge of the benchmark and no design steering; one was built
by hand. Each also has one follow-up change written the same way. A
human labelled 51 design decisions (32 whole-project, 19 in the changes),
with sample good / partial / wrong answers, and decided which ones are
**must-know**. For the change labels, priorities were set blind: the AI's
suggested priorities were hidden and the order shuffled. The human
disagreed with the AI's suggestions on 10 of 19.

**Protocol.** The eval runs exactly the pipeline users get, three runs
per project (model output varies), and reports mean ± spread. A change
is kept only if it helps without regressions. Grader changes are
compared by replaying the grader on stored answer keys, so extraction
noise doesn't hide the effect. No benchmark content ever goes into
prompts.

## What the measurements taught

| Change | Result |
|---|---|
| Ask about *safeguards* the code depends on, not just risks | recall 52% → 74% |
| Target each question at the decision's central consequence | must-know found at any rank 63% → 90% (cumulative), recall → 80% |
| Grader rule: never "owned" for a wrong answer | false "owned" 7 → 0 on identical inputs |
| Separate LLM re-ranking call | +3 points, within noise; **rejected** |
| Rank by centrality instead of "security first" | top-3 must-know 72% → 92% |
| Severe security risks first (product choice) | trial app: no-auth #1; whole-project top-3 92% → 81% |
| Grader sees the cited code | fixes a real-use false "missing"; 0 false "owned" kept |
| One scenario per question, asking one thing | top-3 must-know 81% → 89%, grader agreement 74% → 78%, questions 36 → 30 words |

Some findings mattered more than the numbers:

- **The LLM judge was uninformative.** Against 20 human ratings, it
  ranked a human-preferred question above a merely okay one 31% of the
  time, where chance is 50%. Its quality score was demoted to reference
  only, and question quality is checked by hand.
- **The ranking bug was one sentence.** "Weigh security above other
  categories" made peripheral security details outrank core behaviour. A
  second model call to re-rank didn't help, because it inherited the same
  bias; rewriting the instruction did.
- **A planned retrieval layer turned out to be unnecessary.** Reviewing
  only a change's diff, the tool already finds 94–96% of must-know
  decisions at 100% precision, so the repo map, cross-file references and
  agent tools were never built.
- **Real use found what the benchmark couldn't.** On a fresh vibe-coded
  app, the grader marked a *correct* answer "missing": the developer
  knew that `GET /groups` lists every ID, but the answer key didn't
  mention it, and the grader never saw the code. The benchmark's sample
  answers all stayed within the answer key, so it couldn't catch this.
  Giving the grader the cited code fixed it.
- **Some of Must@3 is taste.** A human and a model can reasonably
  disagree about which decision matters most. The whole-project figure
  includes a deliberate trade: severe security issues always come first,
  even where the labeller had rated them secondary.

## Current results

| Suite | Must@3 | Must(any) | Recall | Precision |
|---|---|---|---|---|
| Whole project (32 labels) | 89% | 92% | 79% | 100% |
| One change, diff only (19 labels) | 62% | 96% | 94% | 100% |

The grader agrees with labelled sample answers 78% of the time. It errs
toward "partial" for good answers. Of 258 wrong or surface-level sample
answers, it graded 1 as owned: a borderline answer that is only wrong
outside the question's scenario, and graded partial or missing in 9 of 9
re-grades.

## Limits

- **Small benchmark:** 51 labels, one human labeller. The spread between
  runs (often ±15–25 points on Must@3) means small improvements can't be
  told apart from noise.
- **Small projects:** each fits in one context window. Very large
  changes are truncated, with a warning.
- **The grader is conservative.** Good answers are often graded
  "partial". Narrower questions helped, but a quarter to a half still
  have a second part.
- **Privacy:** code is sent to the OpenAI API.

## What I'd do next

Try it on more real repositories and people, which is where the most
useful finding so far came from. Then a larger, multi-labeller benchmark
before tuning ranking or questions any further.
