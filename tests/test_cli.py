import json

from accountscope.cli import main
from tests.helpers import make_mbox

BANK = (
    "From: Example Bank <alerts@example.com>\nTo: me@gmail.com\nDelivered-To: me@gmail.com\n"
    "Date: Tue, 03 Sep 2024 10:15:00 +0000\nSubject: Your statement is ready\nContent-Type: text/plain\n\n"
    "Your Visa card ending in 4421 was charged.\n"
)
BANK_OLD = (
    "From: Example Bank <alerts@example.com>\nTo: old@isp.net\n"
    "Date: Fri, 04 Jan 2019 10:15:00 +0000\nSubject: 123456 is your OTP\nContent-Type: text/plain\n\n"
    "We sent a code to your phone number ******7788.\n"
)
NEWS = (
    "From: Deals <deals@shop.example>\nTo: me@gmail.com\nDate: Mon, 01 Jan 2024 00:00:00 +0000\n"
    "Subject: Big sale\nList-Unsubscribe: <mailto:u@shop.example>\nContent-Type: text/plain\n\nSale!\n"
)
FRIEND = (
    "From: Jordan <jordan@gmail.com>\nTo: me@gmail.com\nDate: Wed, 05 Mar 2025 09:00:00 +0000\n"
    "Subject: Your receipt from the pub\nContent-Type: text/plain\n\nYou owe me a pint.\n"
)


def build(tmp_path):
    msgs = [BANK] * 3 + [BANK_OLD] + [NEWS] * 2
    return make_mbox(tmp_path, msgs)


def test_scan_writes_outputs_and_summary(tmp_path, capsys):
    path = build(tmp_path)
    code = main(["scan", str(path), "--me", "old@isp.net", "--csv"])
    out = capsys.readouterr().out
    assert code == 0
    assert "messages: 6" in out and "me@gmail.com" in out
    data = json.loads((tmp_path / "accountscope.json").read_text())
    assert data["schema"] == "accountscope/1"
    bank = next(o for o in data["organisations"] if o["key"] == "example.com")
    assert {w["address"] for w in bank["writes_to"]} == {"me@gmail.com", "old@isp.net"}
    facts = {(h["fact"], h["value"]) for h in bank["holds"]}
    assert ("card", "ending 4421") in facts and ("phone", "ending 7788") in facts
    assert (tmp_path / "accountscope.html").exists() and (tmp_path / "accountscope.csv").exists()


def test_scan_rejects_non_mbox(tmp_path, capsys):
    p = tmp_path / "x.txt"
    p.write_text("nope")
    assert main(["scan", str(p)]) == 2
    assert "mbox" in capsys.readouterr().err


def test_scan_without_recipients_explains_me_flag(tmp_path, capsys):
    path = make_mbox(tmp_path, ["From: a@b.org\nSubject: hi\n\nbody\n"])
    assert main(["scan", str(path)]) == 2
    assert "--me" in capsys.readouterr().err


def test_change_email_reads_inventory_only(tmp_path, capsys):
    path = build(tmp_path)
    assert main(["scan", str(path), "--me", "old@isp.net", "--no-html"]) == 0
    capsys.readouterr()
    out_md = tmp_path / "checklist.md"
    code = main(["change", "email", "old@isp.net", "new@example.org", str(tmp_path / "accountscope.json"), "--out", str(out_md)])
    assert code == 0
    term = capsys.readouterr().out
    assert "Example Bank" in term
    assert "- [ ] **Example Bank**" in out_md.read_text()


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as e:
        assert e.code == 0
    assert "0.1.0" in capsys.readouterr().out


def test_change_rejects_short_card_value(tmp_path, capsys):
    path = build(tmp_path)
    assert main(["scan", str(path), "--me", "old@isp.net", "--no-html"]) == 0
    capsys.readouterr()
    code = main(["change", "card", "4", str(tmp_path / "accountscope.json")])
    assert code == 2
    err = capsys.readouterr().err
    assert "accountscope:" in err
    assert "4 digits" in err


def test_change_rejects_non_object_inventory(tmp_path, capsys):
    inv = tmp_path / "inv.json"
    inv.write_text("[]")
    code = main(["change", "email", "old@isp.net", str(inv)])
    assert code == 2
    assert "unsupported inventory" in capsys.readouterr().err


def test_change_rejects_corrupt_inventory(tmp_path, capsys):
    inv = tmp_path / "inv.json"
    inv.write_text("{not json")
    code = main(["change", "email", "old@isp.net", str(inv)])
    assert code == 2
    assert "cannot read inventory" in capsys.readouterr().err


def test_scan_drops_personal_mail_senders(tmp_path, capsys):
    path = make_mbox(tmp_path, [BANK] * 3 + [BANK_OLD] + [NEWS] * 2 + [FRIEND])
    assert main(["scan", str(path), "--me", "old@isp.net", "--no-html"]) == 0
    out = capsys.readouterr().out
    assert "1 personal-mail senders" in out
    data = json.loads((tmp_path / "accountscope.json").read_text())
    assert "gmail.com" not in [o["key"] for o in data["organisations"]]
    assert "jordan@gmail.com" not in json.dumps(data)
    assert data["source"]["personal_senders_skipped"] == 1
