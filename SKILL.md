---
name: the-council
description: "Puts a hard decision in front of five advisors with opposing lenses, has their answers reviewed blind, and lets an Arbiter issue the verdict. Manual only, so no credits are spent on runs nobody asked for: /the-council [lite] <question>."
disable-model-invocation: true
---

# The Council

The council puts one decision in front of five advisors who look at it from opposing angles. Their answers are reviewed blind, and an Arbiter weighs everything into one verdict. Use it for decisions with real stakes and no obvious answer. Don't use it for facts, writing tasks or summaries.

## modes

- **full** (default): framing checker, 5 advisors, 5 reviewers, Arbiter. 12 sub-agent calls.
- **lite** (`/the-council lite <question>`): skips peer review. 7 calls. Cheaper, but it loses the blind spots peer review finds; the Arbiter fills that section from its own reading of the five answers. Title the verdict `The Council's Verdict (lite): {short topic}`.

## advisors

### 1. Dissenter

A deliberate pessimist. Looks only at what is wrong with the idea and what can go wrong, and leaves the strengths to the others. Finds the weakest assumption the plan rests on, walks through the most likely way it breaks down, and asks what a wrong call would cost and whether it can be undone. Asks the uncomfortable question the user seems to be avoiding.

### 2. Essentialist

Stays on the core of the matter and keeps pulling the discussion back to it. Asks what the user is really after, sorts the facts in the question from the assumptions mixed in with them, and reduces the question to the few decisions that actually move that goal. Ends by stating the decision in a single sentence.

### 3. Visionary

Asks how the idea could be made better and bigger, and looks at it with the widest view of anyone on the council. Proposes concrete ways to improve it, finds the side opportunities it opens, and points out strengths the user already has but takes for granted. Thinks in years rather than weeks, and names what the user gives up by not acting.

### 4. Fresh Eyes

Knows nothing about the user beyond the question itself. First restates the question in plain words, which shows where it is unclear. Flags any word or phrase an outsider wouldn't understand, and asks the obvious question that people close to the topic skip. Gives a first-impression call (yes or no, or which option it would pick) with a reason, then reacts the way the intended customer or reader would on first contact.

### 5. Operator

Asks what carrying out the plan would take in practice. Lists the time, money, skills and people it needs and compares that with what the user has. Finds the bottleneck that will hold the work back first and says how to get through it.

**Why these five:** Dissenter and Visionary pull in opposite directions (what goes wrong vs. how it gets better); Essentialist and Operator check each other (what matters vs. what it takes); Fresh Eyes sees what all four are too close to notice.

The script reads each description, so keep it to one paragraph directly under its `### N. Name` heading.

## models

The Arbiter and the framing checker always run on `opus`. The five advisors share a fixed pool of 2 `opus`, 2 `sonnet` and 1 `haiku`, which the script shuffles on every run, so no role is tied to one model. Each reviewer runs on the same model as its advisor. Use only these three models; `fable` is left out on purpose (cost).

## how a run works

Every sub-agent prompt comes from `scripts/council.py`, which fills the files in `templates/`. Call it as `python "<skill-dir>/scripts/council.py" <command> <run-dir>`, where `<skill-dir>` is this skill's base directory. Write each text once into the run folder and let the script copy it into every prompt that needs it; never paste answers into prompts by hand. The script also puts today's date at the top of each prompt, since sub-agents don't know it.

Spawn every sub-agent with `subagent_type: council-member` and its model, using a one-line prompt: `Read <run-dir>/<prompt-file> and follow it.` Save each answer verbatim to the file named in its step.

### 1. gather context

Before framing, read up to 5 files that bear on the question: `CLAUDE.md` in the project, the project memory at `~/.claude/projects/<project>/memory/` (start with `MEMORY.md`), any file the user pointed to, earlier transcripts in `council/`, and anything else directly relevant (sales numbers for a pricing question, the budget for a hiring question). Keep the 2-3 that give the advisors concrete facts.

### 2. frame the question

Rewrite the user's question as a neutral brief with four parts: the decision to be made, what the user said about it, the facts from step 1, and what is at stake. Add no opinion and no hint of a preferred answer. If the question is too vague to frame, ask the user one clarifying question, then continue without further questions.

Run `init <base-dir>` (the session's scratchpad directory, or `council/.runs` in the project root if there is none). It prints the run folder. Write the brief to `framed.md` and the user's question, word for word, to `raw.md`.

### 3. check the framing

Run `check <run-dir>`, spawn the framing checker with `prompt-check.md`, and save its answer to `check.md`. If it starts with `CHECK: FIX`, apply the fixes to `framed.md`, keeping only claims you can trace to a file from step 1. Check once; don't re-check and don't ask the user.

### 4. run the advisors

Run `advisors <run-dir>`. It shuffles the model pool, writes the result to `models.md` and prints it, then writes `prompt-advisor-<slug>.md` for each advisor. Fresh Eyes gets only `raw.md`, without the brief or any context. Spawn all five at once, each on its model from `models.md`, and save each answer to `response-<slug>.md`.

### 5. peer review (full mode only)

Run `reviews <run-dir>`. It hides the four ranked advisors (Dissenter, Essentialist, Visionary, Operator) behind the letters A-D, in a different fixed order for each reviewer, and writes `prompt-review-<slug>.md` for all five lenses. Fresh Eyes reviews too, but its own answer is not ranked: reviewers have context it never had and would mark it down for that. Spawn all five reviewers at once, each on its advisor's model, and save each answer to `review-<slug>.md`.

### 6. arbiter

Run `arbiter <run-dir>` (add `--lite` in lite mode). It tallies the rankings with a Borda count (4 points for first place down to 1 for last), skips each reviewer's points for its own advisor, prints the tally, and writes `prompt-arbiter.md`. Check the tally for reviews it left out, then spawn the Arbiter. `templates/arbiter.md` defines the verdict's seven sections.

### 7. show the verdict

Post the verdict in chat as markdown, in the language the user wrote in, headings included. Create no other files apart from the optional transcript. Layout:

```
## The Council's Verdict: {short topic}
### Where the Council Agrees
### Where the Council Clashes
### Blind Spots the Council Caught
### The Recommendation
### Confidence
### Questions Only You Can Answer
### The One Thing to Do First
```

### 8. transcript (optional)

Only when the user asks, or when the decision is one they will likely look back on: save the verdict to `<run-dir>/verdict.md`, then run `transcript <run-dir> council/council-transcript-<timestamp>.md` from the project root.

## rules

- Spawn the advisors together, and the reviewers together; one after another only wastes time.
- Always pass `model`. Without it, every sub-agent runs on the main session's model.
- Always use `council-member`. A general-purpose agent loads every tool definition and costs about 37K tokens per call instead of 5K.
- If a sub-agent fails or returns nothing, retry it once on the same model. If it fails again: for an advisor, write `[No response: this advisor failed twice.]` to its response file; for a reviewer, write nothing (the tally notes the gap); for the checker, go on with the unchecked brief. Name every skipped member in the verdict. If two or more advisors fail, stop before the Arbiter and tell the user what failed.
- The Arbiter may side with a minority view when its reasoning is stronger.
- Don't run the council on a question with one right answer; answer it directly.
- Advisors, reviewers and the Arbiter work in English; only the verdict shown to the user is translated.
