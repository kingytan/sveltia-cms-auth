#!/usr/bin/env python3
"""Scan copy for AI writing tells. Reports file:line + rule + the offending words.

Pairs with the stop-slop skill: this finds the lines, stop-slop rewrites them.
Tuned for precision — a scanner that cries wolf gets ignored.

  scan.py                    # files changed vs HEAD (staged, unstaged, untracked)
  scan.py --all              # every copy-bearing file in the repo
  scan.py path [path ...]    # named files or directories
  scan.py --quiet            # findings only, no clean-file noise (for hooks)
  scan.py --json             # machine-readable

Exit 0 = nothing to fix. Exit 1 = findings at "fix" severity.
"""
import argparse, json, os, re, subprocess, sys

TEXT_EXT = {'.json', '.html', '.astro', '.md', '.mdx', '.txt', '.svelte', '.vue'}
SKIP_DIRS = {'node_modules', 'dist', '.git', '.astro', 'vendor', 'banners', 'build', '.next'}

# ---------------------------------------------------------------- extraction

def strip_markup(s):
    s = re.sub(r'<script\b.*?</script>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'<style\b.*?</style>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'<!--.*?-->', ' ', s, flags=re.S)
    s = re.sub(r'\{/\*.*?\*/\}', ' ', s, flags=re.S)
    return s


def untag(s):
    s = re.sub(r'<br\s*/?>', ' ', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    for a, b in (('&amp;', '&'), ('&nbsp;', ' '), ('&mdash;', '—'), ('&minus;', '−'),
                 ('&rarr;', '→'), ('&larr;', '←'), ('&hellip;', '…'), ('&#39;', "'")):
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip()


JUNK = re.compile(r'^(https?:|/|\./|#|[\w.-]+\.(?:png|jpg|webp|mp4|svg|woff2?|html)$)', re.I)


def chunks(path, raw):
    """Yield prose strings worth checking: (text, hint)."""
    ext = os.path.splitext(path)[1].lower()
    out = []
    if ext == '.json':
        try:
            data = json.loads(raw)
        except ValueError:
            return out

        def walk(node, trail):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f'{trail}.{k}' if trail else k)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f'{trail}[{i}]')
            elif isinstance(node, str) and len(node.split()) >= 8 and not JUNK.match(node.strip()):
                for para in node.split('\n\n'):
                    if len(para.split()) >= 8:
                        out.append((para.strip(), trail))
        walk(data, '')
        return out

    body = strip_markup(raw)
    if ext in ('.html', '.astro', '.svelte', '.vue'):
        for m in re.finditer(r'<(p|h1|h2|h3|h4|li|blockquote|figcaption|span|td|dd|summary)\b[^>]*>(.*?)</\1>',
                             body, re.S | re.I):
            t = untag(m.group(2))
            if len(t.split()) >= 8:
                out.append((t, m.group(1)))
        for m in re.finditer(r"['\"]([^'\"\n]{60,})['\"]", body):   # frontmatter / prop strings
            t = m.group(1).strip()
            lead = body[max(0, m.start() - 60):m.start()]
            if 'title' in lead.lower():        # page and og titles are names, not sentences
                continue
            if len(t.split()) >= 8 and not JUNK.match(t):
                out.append((t, 'literal'))
    else:                                                            # md / txt
        body = re.sub(r'```.*?```', ' ', body, flags=re.S)
        body = re.sub(r'^---\n.*?\n---\n', '', body, flags=re.S)
        for para in re.split(r'\n\s*\n', body):
            t = re.sub(r'\s+', ' ', para).strip()
            if len(t.split()) >= 8 and not t.startswith('|'):
                out.append((t, 'para'))
    return out


def sentences(t):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]

# ---------------------------------------------------------------- detectors

NOT_ADVERBS = {
    'only', 'early', 'family', 'apply', 'supply', 'reply', 'comply', 'imply', 'multiply', 'rely',
    'italy', 'july', 'ugly', 'silly', 'holy', 'jolly', 'ally', 'rally', 'belly', 'underbelly', 'jelly', 'anomaly',
    'assembly', 'monopoly', 'panoply', 'melancholy', 'friendly', 'lovely', 'lonely', 'costly',
    'timely', 'orderly', 'elderly', 'deadly', 'worldly', 'homely', 'lively', 'manly', 'curly',
    'burly', 'surly', 'hilly', 'chilly', 'wobbly', 'bubbly', 'fly', 'ply', 'sly', 'shy', 'ally',
    'gly', 'poly', 'supply', 'butterfly', 'wholly',
}
FREQ_ADVERBS = {'daily', 'weekly', 'monthly', 'yearly', 'hourly', 'nightly', 'quarterly'}

BANNED = [
    "here's what", "here's why", "here's the thing", "here's this", "here's that",
    'deep dive', 'deep dives', 'at the end of the day', "it's worth noting", 'game-changer',
    'game changer', 'lean into', 'leaning into', 'moving forward', 'circle back', 'double down',
    'let that sink in', 'make no mistake', 'full stop.', 'the truth is', 'let me be clear',
    'plot twist', "in today's", 'in a world where', 'the reality is', 'at its core',
    'when it comes to', 'the implications are', 'the stakes are high', 'this matters because',
    'navigate the challenges', 'unpack the', 'take a step back', 'on the same page',
]

CONTRAST = [
    (re.compile(r"\bis(?:n't| not)\s+[^.,;]{2,45},\s*(?:it'?s|its)\b", re.I), "isn't X, it's Y"),
    (re.compile(r"\b(?:are|were|was)(?:n't| not)\s+[^.,;]{2,45},\s*(?:it'?s|they'?re)\b", re.I), "wasn't X, it's Y"),
    (re.compile(r'\bnot\s+[^.,;]{2,45},?\s+but\s+(?:rather|instead)?\b', re.I), 'not X but Y'),
    (re.compile(r'\bnot just\b', re.I), 'not just X'),
    (re.compile(r"\bdoesn'?t mean\b", re.I), "doesn't mean X"),
    (re.compile(r'\bstops being\b[^.]{0,60}\bstarts being\b', re.I), 'stops being X, starts being Y'),
    (re.compile(r"\b(?:don'?t|doesn'?t)\s+\w+[^.]{0,50}\bbecause they\b", re.I), 'not because X, because Y'),
    (re.compile(r'\bThe (?:question|answer|problem|point) is(?:n\'t| not)\b', re.I), "the X isn't Y"),
]

FALSE_AGENCY = [
    (re.compile(r'\blives or dies\b', re.I), 'lives or dies'),
    (re.compile(r'\bcomes? alive\b', re.I), 'comes alive'),
    (re.compile(r'\bspeaks for itself\b', re.I), 'speaks for itself'),
    (re.compile(r'\bbegs the question\b', re.I), 'begs the question'),
    (re.compile(r'\bthe data tells? us\b', re.I), 'the data tells us'),
    (re.compile(r'\b(?:the|this|that|a|an|its|their)\s+\w+(?:\s+\w+)?\s+'
                r'(rewards?|punishes|demands?|decides?|emerges?|insists?|refuses?|believes?|'
                r'knows?|wants?|remembers?|celebrates?)\b', re.I), 'a thing doing a human verb'),
]

# Explicit irregulars only. A generic \w+en also matches "between", "often", "listen".
PARTICIPLES = (r'\w+ed|built|rebuilt|cut|made|remade|set|shown|written|rewritten|drawn|redrawn|'
               r'taken|given|held|kept|left|sent|put|read|done|torn|worn|sold|told|paid|lost|found|won|'
               r'driven|known|seen|gone|broken|chosen|hidden|spoken|woven|proven|risen|forgotten|'
               r'thrown|grown|blown|beaten|eaten|frozen|stolen|sworn|drawn|flown')
PASSIVE = re.compile(rf'\b(is|are|was|were|be|been|being|gets?|got|getting)\s+'
                     rf'(?:\w+ly\s+)?({PARTICIPLES})\b(?!\s+(?:to\s+\w+|up|out)\b)', re.I)
PASSIVE_OK = re.compile(r'\b(?:is|are|was|were)\s+(?:based|located|situated|aimed|geared|intended|'
                        r'supposed|used|scheduled|allowed|able|worth)\b', re.I)
ELLIPTIC = re.compile(r'^(Built|Designed|Made|Created|Written|Animated|Rebuilt|Shipped|Cut|Paced|'
                      r'Tuned|Adapted|Crafted|Prepped|Delivered|Imagery re-encoded)\b\s+'
                      r'(?:for|in|to|at|with|natively|across|around|from|by|on)\b')
# Where/When/While open subordinate clauses in ordinary sentences ("Where I hand-coded
# a suite it says so"). The crutch the rule is after is the noun-clause opener.
WH_OPEN = re.compile(r'^(What|Which|Who|Whose|Why|How)\b')
SO_OPEN = re.compile(r'^So[ ,]')
EXTREME = re.compile(r'\b(every ?(?:one|body|thing)?|always|never|nobody|no one)\b', re.I)

FIX = {'passive', 'passive-elliptical', 'adverb', 'em-dash', 'banned-phrase',
       'binary-contrast', 'false-agency', 'wh-opener', 'so-opener'}


QUOTED = re.compile(r'“[^”]{0,400}”|"[^"]{0,400}"|‘[^’]{0,400}’')


def quoted_spans(text):
    """Words someone else said, or a line the work itself uses, are quoted material.
    The rules apply to your sentences, not to what sits inside the quote marks."""
    return [(m.start(), m.end()) for m in QUOTED.finditer(text)]


def check(text, hint):
    """Yield (rule, evidence, severity) for one prose chunk."""
    low = text.lower()
    quotes = quoted_spans(text)
    inq = lambda i: any(a <= i < b for a, b in quotes)

    for b in BANNED:
        i = low.find(b)
        if i >= 0 and not inq(i):
            yield 'banned-phrase', b, 'fix'
    # Titles, credits and captions carry no sentence, so their dash is typography.
    if '—' in text and re.search(r'[.!?]', text) and len(text.split()) >= 12 \
            and not re.search(r'\d—\d', text):
        yield 'em-dash', '—', 'fix'
    for m in re.finditer(r'\b[a-z]{4,}ly\b', text, re.I):
        lw = m.group(0).lower()
        if lw in NOT_ADVERBS or inq(m.start()):
            continue
        yield ('adverb', m.group(0), 'check' if lw in FREQ_ADVERBS else 'fix')
    for rx, label in CONTRAST:
        m = rx.search(text)
        if m and not inq(m.start()):
            yield 'binary-contrast', label, 'fix'
    for rx, label in FALSE_AGENCY:
        m = rx.search(text)
        if m and not inq(m.start()):
            yield 'false-agency', m.group(0) if label.startswith('a thing') else label, 'fix'
    for m in PASSIVE.finditer(text):
        if not PASSIVE_OK.match(m.group(0)) and not inq(m.start()):
            yield 'passive', m.group(0), 'fix'
    sents = sentences(text)
    for i, s in enumerate(sents):
        if ELLIPTIC.match(s):
            yield 'passive-elliptical', s.split(',')[0][:48], 'fix'
        if WH_OPEN.match(s) and not s.rstrip().endswith('?'):
            yield 'wh-opener', s.split()[0], 'fix'
        if i > 0 and SO_OPEN.match(s):
            yield 'so-opener', 'So …', 'fix'
    for m in EXTREME.finditer(text):
        yield 'extreme', m.group(0), 'check'
    if len(sents) >= 3 and len(text.split()) >= 30 and len(sents[-1].split()) <= 5:
        yield 'fragment-closer', sents[-1], 'check'

# ---------------------------------------------------------------- plumbing

def line_of(raw, needle):
    i = raw.find(needle[:60])
    return raw.count('\n', 0, i) + 1 if i >= 0 else 1


def suppressed(lines, line):
    """`slop-ok: reason` within two lines silences a finding you've already ruled on,
    so the scanner stays quiet enough to keep trusting."""
    lo, hi = max(0, line - 6), min(len(lines), line + 1)
    return any('slop-ok' in l for l in lines[lo:hi])


def changed_files(root):
    try:
        a = subprocess.check_output(['git', '-C', root, 'diff', '--name-only', 'HEAD'], text=True).split()
        b = subprocess.check_output(['git', '-C', root, 'ls-files', '-o', '--exclude-standard'],
                                    text=True).split()
    except subprocess.CalledProcessError:
        return []
    return [os.path.join(root, p) for p in dict.fromkeys(a + b)]


def ignore_patterns(root):
    """Lines from .slopignore: substrings of the repo-relative path to skip.

    Copy you didn't write (pasted job ads, client-supplied legal, vendored docs)
    belongs in here — the scanner should only ever judge your own words.
    """
    p = os.path.join(root, '.slopignore')
    if not os.path.exists(p):
        return []
    return [l.strip() for l in open(p, encoding='utf-8')
            if l.strip() and not l.startswith('#')]


def walk_repo(root):
    hits = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if os.path.splitext(f)[1].lower() in TEXT_EXT:
                hits.append(os.path.join(base, f))
    return hits


def main():
    ap = argparse.ArgumentParser(description='Scan copy for AI writing tells.')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--all', action='store_true', help='scan the whole repo, not just changes')
    ap.add_argument('--quiet', action='store_true', help='findings only (hook mode)')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--max', type=int, default=60, help='cap findings printed')
    ap.add_argument('--severity', choices=['fix', 'all'], default='all')
    ap.add_argument('--exclude', action='append', default=[],
                    help='path substring to skip (repeatable); .slopignore does the same')
    a = ap.parse_args()

    root = os.getcwd()
    targets = []
    for p in a.paths:
        targets.extend(walk_repo(p) if os.path.isdir(p) else [p])
    if not targets:
        targets = walk_repo(root) if a.all else changed_files(root)
    skips = ignore_patterns(root) + a.exclude
    targets = [t for t in targets
               if os.path.splitext(t)[1].lower() in TEXT_EXT
               and os.path.isfile(t)
               and not any(f'{os.sep}{d}{os.sep}' in t for d in SKIP_DIRS)
               and not any(s in os.path.relpath(t, root) for s in skips)]

    findings, seen = [], set()
    for path in sorted(set(targets)):
        try:
            raw = open(path, encoding='utf-8').read()
        except (OSError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, root)
        lines = raw.split('\n')
        for text, hint in chunks(path, raw):
            line = line_of(raw, text)
            if suppressed(lines, line):
                continue
            for rule, ev, sev in check(text, hint):
                if a.severity == 'fix' and sev != 'fix':
                    continue
                # A marquee repeats its strip; one finding per (place, rule, words).
                key = (rel, line, rule, ev)
                if key in seen:
                    continue
                seen.add(key)
                findings.append({'file': rel, 'line': line, 'rule': rule, 'evidence': ev,
                                 'severity': sev, 'where': hint, 'context': text[:150]})

    if a.json:
        print(json.dumps(findings, indent=1, ensure_ascii=False))
        return 1 if any(f['severity'] == 'fix' for f in findings) else 0

    fix = [f for f in findings if f['severity'] == 'fix']
    if not findings:
        if not a.quiet:
            print(f'slop-scan: clean ({len(targets)} file(s))')
        return 0

    order = {'fix': 0, 'check': 1}
    for f in sorted(findings, key=lambda x: (order[x['severity']], x['file'], x['line']))[:a.max]:
        mark = '!' if f['severity'] == 'fix' else '~'
        print(f"{mark} {f['file']}:{f['line']}  {f['rule']:<19} {f['evidence']!r}")
        if not a.quiet:
            print(f"    {f['context']}")
    if len(findings) > a.max:
        print(f'  … {len(findings) - a.max} more (raise --max)')
    tally = {}
    for f in findings:
        tally[f['rule']] = tally.get(f['rule'], 0) + 1
    print('slop-scan: ' + ', '.join(f'{k} {v}' for k, v in sorted(tally.items(), key=lambda kv: -kv[1])))
    print('  ! = fix it (stop-slop rules)   ~ = judgement call, often fine')
    return 1 if fix else 0


if __name__ == '__main__':
    sys.exit(main())
