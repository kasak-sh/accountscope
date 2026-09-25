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


def test_classify_with_empty_rules_returns_other():
    empty_rules = {"types": [], "translations": {}}
    assert classify("Verify your email address", False, rules=empty_rules) == "other"


def test_classify_with_empty_rules_and_unsubscribe_returns_marketing():
    empty_rules = {"types": [], "translations": {}}
    assert classify("Verify your email address", True, rules=empty_rules) == "marketing"
