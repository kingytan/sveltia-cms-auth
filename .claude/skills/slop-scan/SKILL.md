---
name: slop-scan
description: "Scan a repo's copy files for AI writing tells and report them as file:line findings — passive voice, adverbs, em dashes in prose, binary contrasts, false agency, Wh- openers, jargon. Run it after ANY copy change: site content JSON, page templates, decks, notes, READMEs, marketing pages. Use when King edits, adds or reviews copy, asks to check writing, ships site content, or asks whether something 'sounds like AI'. Finds the lines; the stop-slop skill rewrites them."
metadata:
  created: 2026-08-19
  pairs-with: stop-slop
---

# Slop scan

Grep for AI writing tells across a repo's copy, with line numbers. Built after the
full kingtan.com.au copy pass on 2026-08-19, where 59 slop lines were found by reading
7,600 words by hand. This finds most of them in under a second.

**Division of labour:** this skill locates. `stop-slop` rewrites. Never rewrite from a
finding alone — read the whole paragraph first, because half the fix is what the
sentence next to it already says.

## Run it

`SCAN=.claude/skills/slop-scan/scripts/scan.py`, in whichever repo you're standing in.
Like `stop-slop`, this skill is vendored per repo rather than installed once: a repo's
`.claude/skills/` only loads for sessions rooted in that repo, so a copy lives in all
fifteen of King's repos (vendored everywhere 2026-09-12). Keep the copies in step: edit
one and you have to edit them all, or a session in one repo runs older rules than the
session next door and neither of them says so.

```bash
python3 $SCAN                       # files changed vs HEAD
python3 $SCAN --all                 # whole repo
python3 $SCAN src/content public/decks
python3 $SCAN --severity fix --quiet   # hook mode
```

No arguments means "what I just changed", which is the mode to use after a copy edit.
Exit 1 when anything at `fix` severity remains, so it gates a hook or a CI step.

Reads `.json` (content collections), `.html`, `.astro`, `.md`, `.mdx`, `.txt`, `.svelte`,
`.vue`. Skips `node_modules`, `dist`, `banners`, `.astro`, `vendor`.

## Reading the output

```
! src/content/work/aldi.json:14  false-agency  'display lives or dies'
    Retail display lives or dies on legibility. I tuned type hierarchy…
slop-scan: passive 3, adverb 2, false-agency 1
```

- `!` **fix** — passive voice, adverbs, em dashes in prose, banned phrases, binary
  contrasts, false agency, Wh- and "So" openers. These break the rules outright.
- `~` **check** — lazy extremes (every/always/never), frequency adverbs (daily, weekly),
  short fragment closers. Often correct. "Every Australian" in an AEC brief is a fact,
  not a sweeping claim.

## Rulings baked in

- **Em dashes: prose only.** Page titles, press credits and year ranges keep theirs
  ("Notes — King Tan", "Sydney Metro launch — Transport for NSW", "2025—26"). The scanner
  skips any string with no sentence-ending punctuation, and any `title`/`og:title`.
- **Quoted material is exempt.** A campaign's own strategy line, a client's words, a
  question you asked yourself: what sits inside “ ” is reported speech, so the rules stop
  at the quote mark. "The barrier isn't information, it's intimidation" stays.
- **`.slopignore`** at the repo root, one path substring per line, for copy that isn't
  yours to rewrite. kingtan-com-au ignores `src/data/job-radar/` (pasted job ads),
  `public/banners/` and `kids-maths/`.

## What it cannot see

Run your own eye over these; no regex reaches them:

- **Pull-quote closers.** A paragraph ending on a quotable fragment with no new
  information ("Same beat in every placement.", "Engineered, the way an Audi layout
  should feel."). The single most common tell in portfolio copy.
- **Repetition between fields.** An overview and a process section opening on the same
  sentence.
- **Metronomic structure.** Twenty-five project pages, all two paragraphs, all the same
  length, all opening on "I".
- **Three-item lists** used for rhythm rather than because there are three things.
- **Vague nouns doing real work** ("real things", "a creative partner").

## After a scan

1. Read each flagged paragraph whole.
2. Rewrite with `stop-slop` loaded. Name the actor, cut the adverb, state the positive.
3. Rescan. Aim for zero `!`, and decide each `~` on purpose rather than by default.
4. On a site: build, screenshot anything whose length changed (headlines wrap), then ship.

## Install the hook (fires on every copy change)

Project `.claude/settings.json`, so it only runs where copy lives:

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit",
      "hooks": [{
        "type": "command",
        "command": "S=\"$HOME/.claude/skills/slop-scan/scripts/scan.py\"; [ -f \"$S\" ] && python3 \"$S\" --severity fix --quiet --max 12 >&2 || true"
      }]
    }]
  }
}
```

Advisory, never blocking: findings go to stderr for Claude to read and act on, and a
missing script is a silent no-op on machines without the skill.

## History

- **2026-08-19** — built during the site-wide copy pass. First run on the freshly cleaned
  site found three more misses in ninety seconds: two deck meta descriptions opening on
  "How", and an elliptical "Built to government ad-spec…" in the AEC 2022 process copy.
  Detector notes from that session: a generic `\w+en` participle pattern matches
  "between" and "often", so passives use an explicit irregular list; Where/When open
  ordinary subordinate clauses and were dropped from the Wh- rule; a repeated marquee
  strip reports the same line four times without deduping.
