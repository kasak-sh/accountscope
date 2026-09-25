from accountscope.orgs import OrgIdentity, identify, load_relays, registrable_domain


def test_registrable_domain_handles_multi_label_suffixes():
    assert registrable_domain("alerts.example.co.uk") == "example.co.uk"
    assert registrable_domain("mail.example.com") == "example.com"
    assert registrable_domain("example.com") == "example.com"
    assert registrable_domain("localhost") == "localhost"
    assert registrable_domain("Foo.Example.COM.") == "example.com"


def test_registrable_domain_known_public_suffixes():
    assert registrable_domain("something.github.io") == "something.github.io"
    assert registrable_domain("co.uk") == "co.uk"


def test_identify_plain_sender():
    ident = identify("alerts@mail.example.com", "Example Bank", "", load_relays())
    assert ident == OrgIdentity(key="example.com", name="Example Bank", via_relay=False)


def test_identify_relay_uses_reply_to_domain():
    ident = identify("bounce@em1234.sendgrid.net", "Acme Shop", "help@acme.example", load_relays())
    assert ident.key == "acme.example" and ident.via_relay is True and ident.name == "Acme Shop"


def test_identify_relay_without_reply_to_slugs_display_name():
    ident = identify("bounce@mcsv.net", "Weekly Digest!", "", load_relays())
    assert ident == OrgIdentity(key="weekly-digest", name="Weekly Digest!", via_relay=True)


def test_identify_missing_sender():
    ident = identify("", "", "", load_relays())
    assert ident.key == "unknown"
