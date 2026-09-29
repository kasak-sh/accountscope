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
