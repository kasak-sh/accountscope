# accountscope

You have no list of which websites and companies you have signed up with over the
years, or which email address, phone number, home address or card each one is
using. So every time one of those changes, or a relative dies, you spend weeks
hunting through your inbox to find them all.

accountscope reads a mailbox export and builds that list. It never touches the
network.

```
$ accountscope scan takeout.mbox

messages: 25   skipped: 0 malformed, 0 without recipients, 0 bodies unreadable, 1 personal-mail senders
dates:    2019-01-04 to 2026-08-18

your addresses (inferred from recipient headers; fix with --me / --not-me):
  me@gmail.com                                   20 messages  aliases: me+bank@gmail.com
  old@isp.net                                     5 messages

organisations: 6   (1 newsletters only)
  finance: 1   shopping: 1   utilities: 1   travel: 1   government: 1   other: 1

most active accounts (transactional mail)
  messages  last seen   holds                  organisation
         8  2026-08-18  card, phone            Example Bank (example.com)
         5  2025-06-21  address, card          Example Store (store.example)
         2  2024-11-01  card                   City Power (citypower.example)
         2  2025-08-20  -                      GoTrip Travel (gotrip.example)
         2  2025-03-06  -                      Tax Office (gov.example)
         0  2025-02-01  -                      Weekly Deals (weeklydeals.example)

written:
  accountscope.json
  accountscope.html
```

(Real output from a 25-message sample mailbox with fictional senders and
addresses — the shape is the same at 184,000 messages, just with more rows. The
25th message is from a friend on gmail.com; that is the one personal-mail sender
counted on the first line and left out of the inventory.)

## What it records that nothing else does

For every organisation, **which of your own addresses it writes to** and when it
last did, read from the To, Cc, Delivered-To, X-Original-To, Envelope-To and
X-Envelope-To headers. That is what turns the inventory into a migration list:

```
$ accountscope change email old@isp.net new@example.org accountscope.json --out checklist.md

change email: old@isp.net -> new@example.org

  tier last        organisation                       reason
  1    2025-03-06  Tax Office                         writes to old@isp.net
                                                      https://gov.example
  1    2019-01-04  Example Bank                       writes to old@isp.net · holds card ending 9876, phone ending 7788
                                                      https://example.com
  2    2024-11-01  City Power                         writes to old@isp.net · holds card ending 3345
                                                      https://citypower.example

written: checklist.md
```

Also recorded, conservatively and with the evidence snippet: whether the
organisation holds a card (as "ending 4421"), a phone number (masked tail), or
a postal address (town and postcode line). Card and phone triggers — "card",
"visa", "mastercard", "amex", "debit", "credit" for a card; "code", "text",
"sms", "message" near "phone", "mobile" or "number" for a phone — are matched
as whole words, so "cardiff" or "postcode" never fire one by mistake. An
address line is kept only when it carries a recognisable postcode: a UK
postcode, a US ZIP or an Indian PIN wins first, and a bare four-digit postcode
(Australia, New Zealand, and several other European formats) is used only if
none of those match. A phone hit is kept only when the message left at least
four digits of the tail visible; "ending 12" identifies nothing, so it is
dropped. Full numbers are never reconstructed.

`accountscope change card <old>` and `accountscope change phone <old>` both
need at least the last four digits of the value you're changing from; give it
fewer and the command exits with status 2 instead of guessing which account
you mean.

Message types come from a small ordered rule set, tried in this order: `otp`,
`verify`, `reset`, `signup`, `notice`, `receipt`, `statement` — the first rule
whose words appear in the subject line wins (a one-time code is always typed
`otp`, even though its subject also says "verification"), with `marketing`
and `other` as the fallback for everything the rules don't recognise. `otp`
additionally needs a 4-8 digit token close to the trigger word — within 30
characters after it, or opening the subject as in "483920 is your OTP" — and
never fires on a message that carries a List-Unsubscribe header, so
"Order 12345678 shipped, use code later" is a `notice` and "use code SAVE20
before 2026 ends" is a newsletter.

## Privacy

accountscope opens no network connection. The public-suffix list and the
[JustDeleteMe](https://justdeleteme.xyz) data it uses are bundled at release
time. The test suite makes `socket.socket` raise, so any change that opens a
connection fails the tests (`tests/conftest.py`). The JSON it writes contains
no full message bodies, no subjects and no third-party recipient addresses;
for each organisation at most the five most frequent sender addresses are
kept.

Mail from a personal-mail provider — gmail.com, outlook.com, yahoo.com,
icloud.com, proton.me and the rest of the list in `data/rules.json` — is
excluded from the inventory entirely, so your friends and family never become
"organisations" and their addresses are never written to disk. The summary line
reports how many such senders were dropped. The known cost: a small business
that mails you from a free-mail address is missed along with them.

For the organisations that remain, at most the five most frequent sender
addresses are recorded, so a domain that mails you from hundreds of per-ticket
or per-customer addresses does not turn the record into an address book. Each
held fact carries one evidence snippet of at most 120 characters from the
message that established it, so you can check the fact; digit runs of seven or
more in that snippet are masked to their last four characters, and nothing else
from a body is kept. The HTML viewer embeds that same JSON once, inside a `<script type="application/json">` tag
with `<`, `>` and `&` escaped the way Django's `json_script` template filter
does it, so nothing in an organisation name, holds value or address line can
break out of the tag. Its address filter is a plain selector over your own
addresses — the ones listed under "your addresses" above — so picking one
shows only the organisations that still write to it.

## Getting your mbox

- **Gmail**: [Google Takeout](https://takeout.google.com) → deselect all →
  select Mail → "All mail data included" → export. You get one `.mbox` file
  (often many GB; that is fine, accountscope streams it).
- **Thunderbird**: install ImportExportTools NG, right-click a folder → Export
  folder → mbox. Thunderbird can also pull an IMAP account down first, which is
  the route for Outlook.com, Yahoo and most ISP mailboxes.

**Name every address you have ever used, at scan time.** Pass each one with its
own `--me`:

```
$ accountscope scan takeout.mbox --me me@gmail.com --me old@isp.net --me me@university.edu
```

accountscope infers your own addresses from how much mail they received, so an
address you abandoned years ago can fall below that threshold and be treated as
someone else's — and every organisation that still writes to it then drops out
of the `change email` checklist, which is the one list you needed it for.
`accountscope change email <old>` warns on stderr when `<old>` is not among the
addresses the scan recorded.

## Install

```
pip install accountscope
```

Python 3.10 or newer. No dependencies.

## Precision

| Date | Version | Organisations correct | Held facts correct | Sample |
|---|---|---|---|---|
| (run docs/precision.md before the first release) | 0.1.0 | – | – | 100 orgs of one 10-year mailbox |

See `docs/precision.md` for the method, and `tests/test_precision.py` for the
labelled-set gate that runs on every commit.

## Not in v1

IMAP, Apple Mail `.emlx` folders, Outlook `.pst`, password-manager import, the
"if I'm gone" family export, a GUI, and anything that logs in or changes an
account for you. The tool produces the list and the links.

## Licence

MIT
