import pytest

from accountscope.classify import TRANSACTIONAL, classify, load_rules


@pytest.mark.parametrize(
    "subject,unsub,expected",
    [
        ("Your verification code is 483920", False, "otp"),
        ("123456 is your OTP", False, "otp"),
        ("Verify your email address", False, "verify"),
        ("Please confirm your account", False, "verify"),
        ("Reset your password", False, "reset"),
        ("Welcome to Example!", False, "signup"),
        ("Your receipt from Example", False, "receipt"),
        ("Order #4521 confirmed", False, "receipt"),
        ("Your statement is ready", False, "statement"),
        ("Your order has shipped", False, "notice"),
        ("Autopay reminder", False, "notice"),
        ("Big spring sale!", True, "marketing"),
        ("Big spring sale!", False, "other"),
        ("Su código es 998877", False, "otp"),
        ("Bem-vindo à Loja", False, "signup"),
        ("Ihre Rechnung", False, "receipt"),
        ("आपका ओटीपी 4455 है", False, "otp"),
    ],
)
def test_classify(subject, unsub, expected):
    assert classify(subject, unsub) == expected


def test_transactional_set():
    assert TRANSACTIONAL == frozenset({"otp", "verify", "reset", "signup", "receipt", "statement", "notice"})
    assert "marketing" not in TRANSACTIONAL


def test_rules_load_and_are_ordered():
    rules = load_rules()
    assert [r["type"] for r in rules["types"]] == ["otp", "verify", "reset", "signup", "notice", "receipt", "statement"]


def test_fact_trust_defaults_all_three_fact_types_to_trusted():
    fact_trust = load_rules()["fact_trust"]
    assert set(fact_trust) == {"card", "phone", "address"}
    assert all(v == "trusted" for v in fact_trust.values())


def test_classify_with_empty_rules_returns_other():
    empty_rules = {"types": [], "translations": {}}
    assert classify("Verify your email address", False, rules=empty_rules) == "other"


def test_classify_with_empty_rules_and_unsubscribe_returns_marketing():
    empty_rules = {"types": [], "translations": {}}
    assert classify("Verify your email address", True, rules=empty_rules) == "marketing"


@pytest.mark.parametrize(
    "subject,unsub,expected",
    [
        ("Use code SAVE20 before 2026 ends", True, "marketing"),
        ("Your code is 483920", False, "otp"),
        ("Order 12345678 shipped, use code later", False, "notice"),
        ("Order 12345678 confirmed", False, "receipt"),
        ("Save 20% in 2026 with code SPRING", False, "other"),
        ("483920 is your login code", False, "otp"),
    ],
)
def test_otp_does_not_fire_on_far_away_digits_or_newsletters(subject, unsub, expected):
    assert classify(subject, unsub) == expected


def test_otp_never_fires_on_a_message_with_list_unsubscribe():
    assert classify("Your verification code is 483920", False) == "otp"
    assert classify("Your verification code is 483920", True) == "verify"
