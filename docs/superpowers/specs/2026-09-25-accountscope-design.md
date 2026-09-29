# accountscope — design spec

Date: 2026-09-25. Status: approved in brainstorming, awaiting written review.
Origin: `~/personal-dev/problem-hunt/FINDINGS.md` (pick R1-C02, 2026-09-24).

## 1. Problem and goal

**The problem, in one sentence.** You have no list of which websites and companies you
have signed up with over the years, or which email address, phone number, home address
or card each one is using, so every time one of those changes, or a relative dies, you
spend weeks hunting through your inbox to find them all.

**The goal of v1.** A zero-network command-line tool that reads a mailbox export and
produces (a) an inventory of every organisation that holds an account for you, tagged
with which of your own addresses each one writes to and what it holds, and (b) on
request, a prioritised checklist of the organisations that still point at an old email,
phone, address or card.

**The differentiator.** Reading the recipient headers (To, Cc, Delivered-To,
X-Original-To, Envelope-To) on every message and recording, per organisation, which of
the user's own addresses it writes to and when it last did. No existing tool records
this field. It is also what turns the inventory into a migration list.

**Success criteria.**
- Runs on a 10-year Google Takeout mbox (10-20 GB) on a laptop in minutes, not hours,
  with no runtime dependencies beyond the Python standard library.
- Organisation and message-type classification precision of at least 70% on the
  labelled fixture set; held-fact precision published in the README from a run on one
  real ten-year mailbox before the first release.
- `--change email old new` lists exactly the organisations whose recipient headers
  include the old address, ordered by tier and recency.
- The test suite fails if any code path opens a socket.

## 2. Scope

**In scope for v1.**
- Input: mbox files (Google Takeout, Thunderbird).
- Inventory with message-type counts, first/last seen, `writes_to`, held facts (card,
  phone, postal address) with evidence, category, JustDeleteMe link.
- Outputs: terminal summary, versioned JSON record, single-file HTML viewer, CSV via
  flag, Markdown checklist via `--change ... --out`.
- Rule tables for English subjects plus a second table of Hindi, Spanish, Portuguese,
  German and French subject words for message typing.

**Out of scope for v1** (recorded so they are not re-litigated).
- IMAP, `.eml`/`.emlx` folders, Outlook `.pst`.
- Password-manager CSV import.
- The `--family` redacted export ("if I'm gone" kit).
- A GUI or hosted version.
- Non-English body extraction for held facts.
- Any action that changes an account (logging in, updating details).

## 3. Architecture (approach A: two-pass streaming, in-memory model)

Rejected alternatives: a SQLite intermediate (re-runnable, but writes a second copy of
mail metadata to disk, the surface a privacy tool should not create) and a single pass
that parses every body (runtime dominated by marketing mail, the noisiest input for the
held-fact heuristics).

**Pass 1 (headers only).** Stream the mbox; for each message read sender, subject,
date, the recipient address set, and the List-Unsubscribe flag. Build the self-address
set, the organisation table, message-type counts, and `writes_to`. Keep a per-organisation
list of at most 25 offsets of transactional messages for pass 2.

**Pass 2 (targeted bodies).** For each organisation, open at most 25 transactional
messages (most recent first), take the plain-text part (HTML stripped), and run the
three held-fact extractors. Marketing messages are never opened.

**Memory.** One message in flight at a time; the aggregate is a dict of `Organisation`
records (thousands, not millions). Nothing is written to disk until the report step.

### Modules

| Module | Job | Depends on |
|---|---|---|
| `mbox.py` | Stream an mbox path; yield a light `Message` (sender address, display name, subject, date, recipient set, has_list_unsubscribe, lazy body handle). Skip and count malformed messages. | `mailbox`, `email` (stdlib) |
| `identity.py` | Decide which addresses are the user's own; collapse plus-aliases; apply `--me` / `--not-me`. | nothing |
| `orgs.py` | Sender → organisation key (registrable domain via bundled public-suffix list); unwrap known relays via display name and Reply-To; merge `noreply@`, `billing@` etc. under one key. | `data/public_suffix_list.dat`, `data/rules.json` (relay list) |
| `classify.py` | Message → type from headers and subject only, using ordered rule tables in `data/rules.json`. Pure functions. | `data/rules.json` |
| `facts.py` | Pass-2 extractors for card, phone, postal address over plain text; returns fact, masked value, snippet (≤120 chars), date, confidence. | `html.parser`, `re` |
| `inventory.py` | `Organisation` and `Inventory` dataclasses; aggregation from messages; JustDeleteMe join on registrable domain; category assignment. | `data/justdeleteme.json` |
| `change.py` | Inventory JSON + change request → tiered, recency-ordered checklist rows. | `inventory.py` |
| `report.py` | Terminal summary, JSON (atomic write), HTML (self-contained), CSV, Markdown checklist. | `inventory.py`, `change.py` |
| `cli.py` | argparse; wires the pipeline; exit codes. | all of the above |

Data flows one way: mbox → messages → (identity, orgs, classify) → inventory → facts
enrich inventory → report or change. No module imports one later in the chain.

## 4. Data model and JSON schema

Schema id `accountscope/1`. Example:

```json
{
  "schema": "accountscope/1",
  "generated_at": "2026-10-02T09:14:00Z",
  "source": {"path": "takeout.mbox", "messages": 184211, "skipped": 37,
             "date_range": ["2014-03-02", "2026-09-30"]},
  "self": [{"address": "me@gmail.com", "aliases": ["me+shop@gmail.com"],
            "messages": 181004, "declared": false}],
  "organisations": [{
    "key": "example.com",
    "name": "Example Bank",
    "sender_addresses": ["alerts@example.com", "noreply@example.com"],
    "types": {"signup": 1, "otp": 42, "statement": 96, "marketing": 12},
    "marketing_only": false,
    "first_seen": "2016-05-11", "last_seen": "2026-09-28",
    "writes_to": [{"address": "me@gmail.com", "last": "2026-09-28", "count": 150},
                  {"address": "old@isp.net", "last": "2019-01-04", "count": 1}],
    "holds": [{"fact": "card", "value": "ending 4421",
               "evidence": "your card ending 4421 was charged",
               "seen": "2026-09-01", "confidence": "high"}],
    "delete": {"url": "https://example.com/close", "difficulty": "hard"},
    "category": "finance"
  }]
}
```

Rules for the record:
- `writes_to` is always present and lists only self addresses.
- `holds.value` is stored only in the masked form the email used; the tool never
  reconstructs a full card or phone number. `evidence` is capped at 120 characters.
- `category` ∈ {finance, government, utilities, health, telecom, travel, shopping,
  social, work, other}; rule-based from message mix and a keyword list in `rules.json`.
- `delete` is present only when the JustDeleteMe dataset has an entry for the domain.
- The file never contains full message bodies, subjects, or third-party recipient
  addresses; for each organisation at most the five most frequent sender addresses
  are kept. The only body-derived text is the ≤120-character evidence snippet on
  each held fact.
- Field additions bump the minor schema id (`accountscope/1` → `accountscope/1.1`);
  removals or renames bump the major and the HTML viewer refuses older majors.

## 5. Classification rules

**Self addresses.** Lower-case all recipient addresses; collapse `local+tag@domain` to
`local@domain` but remember the alias. An address is "self" if it received ≥ 2% of all
messages or ≥ 200 messages, or was passed with `--me`. `--not-me` removes an address.
The terminal summary prints the inferred set before anything else.

**Organisation key.** Registrable domain of the sender via the public-suffix list.
If the sender domain is a known relay (SendGrid, Mailchimp, Mailgun, Amazon SES,
Postmark, SparkPost, Constant Contact, HubSpot, Klaviyo, Braze, Iterable, Salesforce
Marketing Cloud, Campaign Monitor, Sendinblue/Brevo, ActiveCampaign, Customer.io,
Mandrill, Zendesk, Intercom, Freshdesk and others listed in `rules.json`), use the
registrable domain of Reply-To if present, else a slug of the display name, and mark
`via_relay: true`. Display name is the human label; the key stays the domain.
A sender whose registrable domain is a personal-mail provider (gmail.com,
outlook.com, yahoo.com, icloud.com, proton.me and the rest of `personal_mail_domains`
in `rules.json`) is not an organisation and is excluded from the inventory entirely,
counted only as `source.personal_senders_skipped`.

**Category.** Each category's keyword list in `rules.json` is split into `exact`
tokens, which must equal a whole domain label or name word (or, for host-shaped and
multi-word tokens, the registrable domain or phrase), and `stem` tokens, which may
additionally match the tail of a domain label (the stem "bank" tags "mybank.com", but
the exact token "wise" does not tag "otherwise.com").

**Message type.** Ordered rules over subject and headers, first match wins; each
trigger word or phrase is matched on Unicode-aware word boundaries, never as a raw
substring (so "reset" no longer fires inside "unresettable", and "confirme" no longer
fires inside "confirmed"):
1. `otp`: subject contains a word from {code, OTP, verification, verify, passcode,
   one-time} — or their listed translations — with a 4-8 digit token within 30
   characters after it, or opening the subject; never on a List-Unsubscribe message.
2. `verify`: {verify, confirm your, activate, validate} without a digit token.
3. `reset`: {reset, forgot, new password, change your password}.
4. `signup`: {welcome, thanks for signing up, account created, you're in, get started}.
5. `notice`: {shipped, delivery, on its way, billing update, autopay, payment due}.
6. `receipt`: {receipt, order, invoice #, payment received, thank you for your purchase}.
7. `statement`: {statement, bill is ready, e-statement, monthly summary, payslip}.
8. `marketing`: List-Unsubscribe header present and no earlier match.
9. `other`: none of the above.
Types 1-7 are "transactional" and eligible for pass 2. An organisation with only
type 8 messages gets `marketing_only: true` but stays in the inventory.

**Held facts (pass 2, plain text, English v1).**
- `card`: `(card|visa|mastercard|amex|debit|credit)[^.]{0,40}(ending( in)?|last (4|four) digits)[^0-9]{0,10}(\d{4})`.
- `phone`: `(code|text|sms|message)[^.]{0,60}(phone|mobile|number)[^0-9*x•]{0,20}([0-9*x•]{6,})` capturing the masked tail only.
- `address`: a 2-4 line block within 300 characters after {ship, shipping, deliver,
  delivery, billing} + {address}, containing a postcode-shaped token (UK, US ZIP,
  Indian PIN, EU 4-5 digits); stored as the town/postcode line only.
Two independent hits on different dates → `confidence: high`; one hit → `medium`.
If labelled precision for a fact type is below 70%, that type is still written to
JSON marked `"inferred": true` but excluded from the change checklist.

## 6. Change checklist

`accountscope --change <email|phone|address|card> <old> [<new>] inventory.json [--out checklist.md]`

Reads the JSON only; never the mailbox.

**Selection.**
- `email`: organisations whose `writes_to` includes `<old>`.
- `phone` / `address` / `card`: organisations with a matching held fact; if `<old>`
  is omitted, every organisation with that fact type, plus every organisation in
  finance, government, utilities and health marked "check".

**Order.** Tier 1: finance, government. Tier 2: utilities, health, telecom, travel.
Tier 3: everything else. Within a tier, by `writes_to.last` for the old address
(most recent first). `marketing_only` organisations come last, collapsed into a
single "newsletters (N)" line.

**Row content.** Organisation name, last date it used the old value, what it holds,
change-it-here link (JustDeleteMe URL if present, else `https://<key>`), and for
"check" rows the reason. Markdown output is a checkbox list.

## 7. Outputs

- **Terminal**: source stats; inferred self addresses with a `--me/--not-me` hint;
  counts by category; ten organisations with the most transactional mail; skip counts;
  output paths. Fits one screen.
- **JSON**: section-4 record, written to `<mbox-dir>/accountscope.json` or `--out-dir`;
  temp-file-then-rename so an interrupted run never leaves a partial file.
- **HTML**: one self-contained file (inline CSS and JS, no external resources) that
  embeds the JSON in a `<script type="application/json">` tag and renders it: grouped
  by category, search box, filter chips (writes to a given address, holds card, holds
  phone, marketing only), per-row delete link. With scripting disabled it still shows
  a plain grouped table, pre-rendered server-side into `<noscript>`.
- **CSV** (`--csv`): one row per organisation with `writes_to` and `holds` flattened.
- **Markdown checklist** from `--change --out`.

## 8. Privacy and error handling

- No module imports `socket`, `urllib`, `http`, `ssl` or `smtplib`. The suffix list and
  JustDeleteMe data are bundled; `scripts/refresh_data.py` is the only network code and
  is not part of the installed package.
- `tests/conftest.py` monkeypatches `socket.socket` to raise for every test.
- Malformed messages: skipped and counted. Not an mbox: exit 2 with a message naming
  what was found. No recipient headers anywhere: exit 2 with an explanation and a
  `--me` suggestion. Body decode failure: message dropped from pass 2 only.
- Every skip category appears in the terminal summary.
- Exit codes: 0 success, 1 unexpected error, 2 bad input.

## 9. Testing

- Pytest; one `tests/test_<module>.py` per module.
- `tests/fixtures/`: hand-written mbox files — Takeout shape, Thunderbird shape,
  plus-aliases, relay senders, no-recipient message, malformed message, one message per
  type and per held fact, one non-English subject per type.
- `tests/labelled/`: ~300 messages with expected organisation, type and facts;
  `test_precision.py` prints precision per type and fact and fails below 70%.
- CLI tests run the real entry point on fixtures and check exit codes, terminal text,
  and that JSON validates against the schema.
- The real-mailbox precision run is a documented manual step in `docs/precision.md`,
  with its numbers copied into the README.

## 10. Repository and release

```
accountscope/
  accountscope/  __init__.py cli.py mbox.py identity.py orgs.py classify.py
                 facts.py inventory.py change.py report.py
                 data/public_suffix_list.dat data/justdeleteme.json data/rules.json
  scripts/       refresh_data.py
  tests/         test_*.py conftest.py fixtures/ labelled/
  docs/          precision.md superpowers/specs/2026-09-25-accountscope-design.md
  pyproject.toml README.md LICENSE CHANGELOG.md
```

- `github.com/kasak-sh/accountscope`, MIT, Python ≥ 3.10, setuptools, no runtime
  dependencies, `pytest>=8` as the only dev dependency, script
  `accountscope = "accountscope.cli:main"`.
- Release notes record the refresh dates of the suffix list and JustDeleteMe data.
- README: the one-sentence problem, a real terminal transcript, the privacy sentence
  pointing at the socket test, precision numbers, and a "how to get your mbox" section
  for Takeout and Thunderbird.

## 11. Kill conditions to re-check before coding

- `lorcanj/find-my-accounts` (GPL-3.0, active) adding recipient-header or held-fact
  classification: contribute upstream instead of building.
- Gmail, Apple Passwords, Google Password Manager or Bitwarden shipping an
  "accounts using this email/phone" view.
- Labelled precision below 70% that cannot be fixed by rule changes.
