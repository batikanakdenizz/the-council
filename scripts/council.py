#!/usr/bin/env python3
"""Prompt builder and ranking tally for the council skill.

The main thread writes each piece of text once into a run folder (the framed
question, each advisor response, each peer review). This script does all the
copying: it fills the prompt templates, shuffles the advisor models, applies
the fixed reviewer orders and computes the Borda tally. Standard library only.

Usage:
  council.py init <base-dir>               create a run folder, print its path
  council.py check <run-dir>               build the framing-checker prompt
  council.py advisors <run-dir>            assign models, build the 5 advisor prompts
  council.py reviews <run-dir>             build the 5 reviewer prompts
  council.py arbiter <run-dir> [--lite]    tally the rankings, build the Arbiter prompt
  council.py transcript <run-dir> <out.md> join the whole run into one markdown file
"""

import datetime
import random
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_DIR / "templates"

NAMES = {
    "dissenter": "Dissenter",
    "essentialist": "Essentialist",
    "visionary": "Visionary",
    "fresh-eyes": "Fresh Eyes",
    "operator": "Operator",
}
# Fresh Eyes answers but is not peer-reviewed or ranked (see SKILL.md, step 5).
RANKED = ["dissenter", "essentialist", "visionary", "operator"]
LETTERS = "ABCD"

# The one task each advisor never skips, filled into templates/advisor.md.
CORE = {
    "dissenter": "say what is wrong with the idea and what can go wrong",
    "essentialist": "state the decision in a single sentence",
    "visionary": "say how the idea could be made better",
    "fresh-eyes": "restate the question in plain words and give your first-impression call",
    "operator": "name the bottleneck",
}

# Shuffled across the five advisors on every run; a fixed pool keeps the cost the same.
MODEL_POOL = ["opus", "opus", "sonnet", "sonnet", "haiku"]

# Letter order each reviewer lens sees. The first four rows form a Latin square:
# every ranked advisor lands in every position exactly once, and each reviewer
# sees its own advisor in a different position. The fresh-eyes row adds one more order.
ORDERS = {
    "dissenter": ["dissenter", "visionary", "operator", "essentialist"],
    "essentialist": ["operator", "essentialist", "dissenter", "visionary"],
    "visionary": ["essentialist", "operator", "visionary", "dissenter"],
    "operator": ["visionary", "dissenter", "essentialist", "operator"],
    "fresh-eyes": ["operator", "visionary", "essentialist", "dissenter"],
}

RANKING_LINE = re.compile(r"FINAL RANKING:\s*([A-D](?:\s*>\s*[A-D]){3})")


def read(path):
    if not path.exists():
        sys.exit(f"missing file: {path}")
    return path.read_text(encoding="utf-8").strip()


def write(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")
    print(path)


def fill(template_name, **values):
    template = read(TEMPLATES / template_name)
    wanted = set(re.findall(r"\{\{(\w+)\}\}", template))
    if wanted != set(values):
        sys.exit(f"{template_name}: placeholders {sorted(wanted)} don't match values {sorted(values)}")
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def descriptions():
    """Advisor descriptions, read from SKILL.md so they live in one place."""
    text = read(SKILL_DIR / "SKILL.md")
    found = dict(re.findall(r"^### \d\. ([^\n]+)\n\n([^\n]+)", text, re.M))
    missing = [name for name in NAMES.values() if name not in found]
    if missing:
        sys.exit(f"advisor descriptions not found in SKILL.md: {missing}")
    return {slug: found[name] for slug, name in NAMES.items()}


def today():
    """Stamped into every prompt: sub-agents don't know the date and guess wrong."""
    return datetime.date.today().strftime("%A, %Y-%m-%d")


def short(slug):
    return NAMES[slug]


def models(run):
    """Slug-to-model table that `advisors` wrote; reviewers reuse their advisor's model."""
    return read(run / "models.md")


def mapping(lens):
    return ", ".join(f"{LETTERS[i]}={short(s)}" for i, s in enumerate(ORDERS[lens]))


def tally(run):
    """Borda count over the reviews, skipping each reviewer's points for its own advisor."""
    scores = {s: 0 for s in RANKED}
    maxes = {s: 0 for s in RANKED}
    notes = []
    for lens, order in ORDERS.items():
        path = run / f"review-{lens}.md"
        if not path.exists():
            notes.append(f"{short(lens)}-lens review is missing and was left out of the tally.")
            continue
        found = RANKING_LINE.findall(path.read_text(encoding="utf-8"))
        letters = re.findall(r"[A-D]", found[-1]) if found else []
        if sorted(letters) != list(LETTERS):
            notes.append(f"{short(lens)}-lens review has no valid FINAL RANKING line and was left out of the tally.")
            continue
        for place, letter in enumerate(letters):
            advisor = order[LETTERS.index(letter)]
            if advisor == lens:
                continue
            scores[advisor] += len(LETTERS) - place
            maxes[advisor] += len(LETTERS)
    return scores, maxes, notes


def ranking_text(scores, maxes, notes):
    ordered = sorted(RANKED, key=lambda s: -scores[s])
    lines = [f"{NAMES[s]}: {scores[s]} / {maxes[s]}" for s in ordered]
    return "\n".join(lines + [f"Note: {n}" for n in notes])


def cmd_init(base):
    run = Path(base) / datetime.datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run.mkdir(parents=True)
    print(run)


def cmd_check(run):
    write(run / "prompt-check.md",
          fill("checker.md", date=today(), raw=read(run / "raw.md"), framed=read(run / "framed.md")))


def cmd_advisors(run):
    desc = descriptions()
    framed = read(run / "framed.md")
    raw = read(run / "raw.md")
    pool = MODEL_POOL[:]
    random.shuffle(pool)
    write(run / "models.md", "\n".join(f"{slug}: {model}" for slug, model in zip(NAMES, pool)))
    print(models(run))
    for slug, name in NAMES.items():
        question = raw if slug == "fresh-eyes" else framed
        write(run / f"prompt-advisor-{slug}.md",
              fill("advisor.md", date=today(), name=name, description=desc[slug], core=CORE[slug],
                   question=question))


def cmd_reviews(run):
    desc = descriptions()
    framed = read(run / "framed.md")
    responses = {s: read(run / f"response-{s}.md") for s in RANKED}
    for lens, order in ORDERS.items():
        block = "\n\n".join(f"**Response {LETTERS[i]}:**\n\n{responses[s]}" for i, s in enumerate(order))
        write(run / f"prompt-review-{lens}.md",
              fill("reviewer.md", date=today(), name=NAMES[lens], description=desc[lens], question=framed,
                   responses=block))
    print(models(run))


def cmd_arbiter(run, lite):
    framed = read(run / "framed.md")
    responses = {s: read(run / f"response-{s}.md") for s in NAMES}
    advisors = "\n\n".join(f"**{NAMES[s]}:**\n\n{responses[s]}" for s in RANKED)
    if lite:
        review_block = ("LITE MODE: there was no peer-review round. Fill \"Blind Spots the Council Caught\" "
                        "from your own cross-reading of the five responses.")
    else:
        reviews = [f"Review, {short(lens)} lens. Mapping: {mapping(lens)}\n\n{read(run / f'review-{lens}.md')}"
                   for lens in ORDERS if (run / f"review-{lens}.md").exists()]
        scores, maxes, notes = tally(run)
        ranking = ranking_text(scores, maxes, notes)
        print(ranking)
        review_block = (
            "PEER REVIEWS of the four ranked advisors (the letters mean different advisors in each review; "
            "the mapping is shown above each one):\n\n" + "\n\n".join(reviews) +
            "\n\nAGGREGATE RANKING (Borda count, 4 points for 1st down to 1 for 4th; each reviewer's points "
            "for its own advisor excluded):\n\n" + ranking +
            "\n\nTreat the ranking as a signal, not a vote. Overrule it when the reasoning supports it."
        )
    write(run / "prompt-arbiter.md",
          fill("arbiter.md", date=today(), question=framed, advisors=advisors, fresh_eyes=responses["fresh-eyes"],
               review_block=review_block))


def cmd_transcript(run, out):
    parts = ["# Council transcript", "## Framed question", read(run / "framed.md"),
             "## Raw question (given to Fresh Eyes)", read(run / "raw.md")]
    if (run / "check.md").exists():
        parts += ["## Framing check", read(run / "check.md")]
    for slug, name in NAMES.items():
        parts += [f"## {name}", read(run / f"response-{slug}.md")]
    reviewed = [lens for lens in ORDERS if (run / f"review-{lens}.md").exists()]
    for lens in reviewed:
        parts += [f"## Review, {short(lens)} lens ({mapping(lens)})", read(run / f"review-{lens}.md")]
    if reviewed:
        parts += ["## Aggregate ranking", ranking_text(*tally(run))]
    if (run / "verdict.md").exists():
        parts += ["## Verdict", read(run / "verdict.md")]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write(out, "\n\n".join(parts))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    commands = {"init": 1, "check": 1, "advisors": 1, "reviews": 1, "arbiter": 1, "transcript": 2}
    if len(argv) < 2 or argv[0] not in commands:
        sys.exit(__doc__)
    command, args = argv[0], [a for a in argv[1:] if a != "--lite"]
    if len(args) != commands[command]:
        sys.exit(__doc__)
    if command == "init":
        cmd_init(args[0])
    elif command == "check":
        cmd_check(Path(args[0]))
    elif command == "advisors":
        cmd_advisors(Path(args[0]))
    elif command == "reviews":
        cmd_reviews(Path(args[0]))
    elif command == "arbiter":
        cmd_arbiter(Path(args[0]), "--lite" in argv)
    else:
        cmd_transcript(Path(args[0]), args[1])


if __name__ == "__main__":
    main(sys.argv[1:])
