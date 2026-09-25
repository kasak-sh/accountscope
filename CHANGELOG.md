# Changelog

## 0.1.0 (unreleased)
- `accountscope scan`: inventory from an mbox with self-address inference,
  organisation identity via the public-suffix list, message typing, `writes_to`
  per organisation, conservative held-fact extraction, JSON/HTML/CSV output.
- `accountscope change`: tiered checklist for an email, phone, address or card change.
- Zero-network guarantee enforced by the test suite.
- Bundled data refreshed 2026-09-25: public suffix list (10,333 rules) and
  JustDeleteMe (3,909 domains), both dated in `accountscope/data/versions.json`.
  The JustDeleteMe index no longer takes the host of a deletion URL when the site
  lists its own domains, so `google.com` resolves to Google rather than Blogger
  and `github.com` to GitHub rather than Bountysource.
