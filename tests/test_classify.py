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
        ("Confirme su cuenta", False, "verify"),
        ("Unresettable widgets on sale", False, "other"),
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


@pytest.mark.parametrize(
    "subject,unsub,expected",
    [
        # German (and other) compounds glue the trigger to a following noun, so a
        # trailing word boundary would lose them. These triggers are listed in
        # rules.json "stem_words" and compile as prefixes.
        ("Ihr Verifizierungscode lautet 483920", False, "otp"),
        ("Versandbestätigung für Ihre Bestellung", False, "notice"),
        ("Ihre Rechnungsnummer 4455", False, "receipt"),
        ("Passwortänderung angefordert", False, "reset"),
        ("Kontoauszugsbenachrichtigung", False, "statement"),
        ("Willkommensangebot", True, "signup"),
    ],
)
def test_compound_nouns_match_stem_triggers(subject, unsub, expected):
    assert classify(subject, unsub) == expected


@pytest.mark.parametrize(
    "subject,unsub,expected",
    [
        # Everything not in "stem_words" keeps both boundaries: a stem list that leaked
        # into the ordinary triggers would break exactly these two.
        ("Unresettable widgets on sale", False, "other"),
        ("Order #4521 confirmed", False, "receipt"),
        ("Confirmed: your seat is booked", False, "other"),
    ],
)
def test_non_stem_triggers_keep_both_word_boundaries(subject, unsub, expected):
    assert classify(subject, unsub) == expected


def test_stem_words_are_all_real_triggers():
    """Every stem word must actually be a trigger somewhere, or it silently does nothing."""
    rules = load_rules()
    triggers = {word for rule in rules["types"] for word in rule["any"]}
    triggers |= {word for words in rules["translations"].values() for word in words}
    assert set(rules["stem_words"]) <= triggers


def test_custom_rules_are_not_cached_so_a_mutation_is_picked_up():
    """An ad-hoc rules dict is compiled on the fly: mutate it and the next call obeys
    the new rules, rather than a stale set of patterns keyed on the dict's identity."""
    rules = {"types": [{"type": "verify", "any": ["verify"]}], "translations": {}}
    assert classify("Verify your email address", False, rules=rules) == "verify"
    rules["types"][0]["any"] = ["activate"]
    assert classify("Verify your email address", False, rules=rules) == "other"
    assert classify("Activate your account", False, rules=rules) == "verify"


def test_module_cache_does_not_grow_with_ad_hoc_rules_dicts():
    from accountscope import classify as classify_module

    classify("Verify your email address", False)  # warm the bundled entry
    before = len(classify_module._pattern_cache)
    for i in range(50):
        rules = {"types": [{"type": "verify", "any": [f"token{i}"]}], "translations": {}}
        classify(f"Please token{i} now", False, rules=rules)
    assert len(classify_module._pattern_cache) == before


def test_bundled_rules_compile_once():
    from accountscope import classify as classify_module

    classify("Verify your email address", False)
    first = classify_module._compiled(load_rules())
    second = classify_module._compiled(load_rules())
    assert first is second
