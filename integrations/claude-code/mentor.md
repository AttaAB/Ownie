---
description: Quiz me on the design decisions in code I didn't write (Engineering Mentor)
argument-hint: "[--uncommitted | --all | --since REF | --more | --revisit] [-n N]"
allowed-tools: Bash(mentor:*)
---

Run an Engineering Mentor review with me. `mentor` finds the design
decisions in my code, asks me about them, and grades my answers. Your job
is only to relay: I have to do the thinking.

Start with:

```
mentor ask $ARGUMENTS
```

It prints JSON with `questions` (each has `id`, `location`, `setup`,
`question`, `code`). If it prints a `message` and no questions, tell me
the message and stop. If `mentor` isn't installed, tell me to run
`pipx install git+https://github.com/AttaAB/engineer-mentor` and stop.

Then, for each question, one at a time:

1. Show the question number, the `location`, the `code` in a code block,
   the `setup`, and the `question`, all word for word. Then stop and wait
   for my reply.
2. Treat my reply as follows:
   - "hint" → run `mentor hint <id>` and show the hint word for word.
   - "explain" → run `mentor explain <id>`, show the explanation, move on.
   - "skip" → run `mentor skip <id>`, move on.
   - "stop" → stop the review (progress is already saved).
   - anything else is my answer → pass my reply exactly as I wrote it,
     on stdin through a quoted heredoc so the shell never interprets it:

     ```
     mentor answer <id> <<'MENTOR_ANSWER'
     <my reply>
     MENTOR_ANSWER
     ```
3. After `mentor answer`, show the `verdict` and `feedback` word for word.
   If `done` is false, tell me I can try again (`attempts_left` left) or
   say hint / explain / skip. If `done` is true, show any `explanation`
   and move on.

When the questions are done, show the ownership score from the last
result (`owned` / `total`) and mention `/mentor --more` for decisions not
asked yet and `/mentor --revisit` for ones I haven't owned yet.

Rules, because the point is that I learn the code:

- Never answer, hint at, or explain a question yourself before I've
  answered it or asked for a hint or explanation. Don't rephrase the
  question to make it easier.
- Never grade my answer yourself or argue with the grade; `mentor answer`
  is the only grader.
- Don't read `.mentor/state.json` or `.mentor/DECISIONS.md` during the
  review; they contain the answers.
- Don't edit any code during the review.
