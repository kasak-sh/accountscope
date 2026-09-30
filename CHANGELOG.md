# Changelog

## 0.1.0 (unreleased)
- `accountscope scan`: inventory from an mbox with self-address inference,
  organisation identity via the public-suffix list, message typing, `writes_to`
  per organisation, conservative held-fact extraction, JSON/HTML/CSV output.
- `accountscope change`: tiered checklist for an email, phone, address or card change.
- Fact trust: a fact type whose precision falls below the bar in `docs/precision.md`
  is marked `inferred` in `rules.json`, which excludes it from `accountscope change`
  and flags it, muted, in the HTML and the CSV.
- Category keywords split into `exact` and `stem` roles, and message-type triggers
  matched on `\w` word boundaries — with a `stem_words` list for the triggers German
  compounds are built on, which match as prefixes.
- A 371-row hand-labelled message set (`tests/labelled/messages.jsonl`) with a
  per-type precision and recall gate and a linter for the file's shape.
- Zero-network guarantee enforced by the test suite.
- Bundled data refreshed 2026-09-25: public suffix list (10,333 rules) and
  JustDeleteMe (3,909 domains), both dated in `accountscope/data/versions.json`.
  The JustDeleteMe index no longer takes the host of a deletion URL when the site
  lists its own domains, so `google.com` resolves to Google rather than Blogger
  and `github.com` to GitHub rather than Bountysource.
