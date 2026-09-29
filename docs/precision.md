# Measuring precision on a real mailbox

accountscope's held-fact and message-type heuristics are only as good as their
precision on real mail. Before each release, run the tool on one real, ten-year
mailbox and record the numbers below. Nothing from the mailbox is committed.

1. Export the mailbox: Google Takeout → Mail → "All mail" as mbox, or in
   Thunderbird right-click the folder → Export (ImportExportTools NG) → mbox.
2. Run `accountscope scan path/to/mail.mbox --out-dir /tmp/scope`.
3. Open `/tmp/scope/accountscope.html`. Sample 100 organisations at random
   (`python3 -c "import json,random;d=json.load(open('/tmp/scope/accountscope.json'));[print(o['key']) for o in random.sample(d['organisations'],100)]"`).
4. For each sampled organisation, judge: is the organisation real and correctly
   named (yes/no); is each `holds` fact true (yes/no, checking the evidence
   snippet against the original mail); is `writes_to` correct.
5. Record: organisation precision = correct / 100; fact precision = true facts /
   all sampled facts. Copy both into the README table with the date and the
   accountscope version.

If fact precision for a fact type is below 70%, set that type's entry in
`accountscope/data/rules.json` `fact_trust` to `"inferred"` (it starts
`"trusted"` for `card`, `phone` and `address`). Facts of that type keep being
written to the JSON and shown, flagged, in the HTML, but `accountscope
change` stops selecting them: an organisation whose only fact of that type is
inferred is treated as if it held no such fact, falling back to a "check"
row where its category warrants one. Also open an issue with the failing
snippets (identifiers replaced).

## Labelled set

Real mailboxes can't be committed, so `tests/labelled/messages.jsonl` is the
next best thing: a hand-labelled set of real-*shaped* messages (fictional
senders, names, phone numbers and addresses only — never a real person or a
real mailbox) that `tests/test_precision.py` checks `classify()` and
`extract_facts()` against on every commit. It is deliberately not tuned to
match `accountscope/data/rules.json` — it includes hard cases (keyword
collisions like a bank newsletter that says "billing update", receipts that
say "verify" or "confirmed", translated subjects, masked/unmasked/malformed
phone and card numbers, address blocks in six countries' formats, and
lookalike non-facts such as "cardio" or a bare 7-digit order number) so that
a regression in the rules shows up as a real number dropping, not as a test
someone had to keep in sync with the code. The two guards do different jobs:
a regression in one keyword is caught by `tests/test_classify.py`, which names
the subject and the type it must produce, while the gate here guards the trend
across the whole set.

Each line is one JSON object:
`{"subject": str, "list_unsubscribe": bool, "body": str, "type": str, "facts": [{"fact": str, "value": str}]}`,
with `type` one of `otp`, `verify`, `reset`, `signup`, `receipt`, `statement`,
`notice`, `marketing`, `other`, and each fact's `fact` one of `card`, `phone`,
`address`.

To add a row: pick the type or fact it's meant to exercise, write it with
fictional identifiers only (`example.com` / `example.org` / `example.net` /
the `.example` TLD, `555`-style phone numbers, names like "A Person"), decide
the *true* label by reading the message the way a person would — not by
running it through `classify()`/`extract_facts()` and copying the answer —
then append it to `tests/labelled/messages.jsonl`. Before committing, run:

```
.venv/bin/python scripts/lint_labelled.py
.venv/bin/python -m pytest tests/test_precision.py -s
```

The linter checks the file's shape (valid JSON, exactly the five keys, a
real `type`, facts restricted to the three known kinds, and no email-shaped
`@domain` outside `example.com`/`.org`/`.net`/`.example`). The `-s` flag shows
the per-type and per-fact precision/recall tables that `test_precision.py`
gates on; if a table shows a real drop, that's a signal to investigate
`rules.json` or the extractors, not to relabel the row.
