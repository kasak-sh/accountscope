from accountscope.facts import EVIDENCE_WIDTH, FactHit, extract_facts, merge_facts


def test_card_ending_is_masked_and_evidenced():
    hits = extract_facts("Hi. Your Visa card ending in 4421 was charged $12.00 today.", "2024-09-01")
    assert hits == [FactHit("card", "ending 4421", "Your Visa card ending in 4421 was charged $12.00 today.", "2024-09-01")]


def test_card_last_four_digits_variant():
    hits = extract_facts("We charged the card with last 4 digits 9876.", "2024-01-01")
    assert hits[0].fact == "card" and hits[0].value == "ending 9876"


def test_phone_masked_tail():
    hits = extract_facts("We sent a code to your phone number ******1234. Enter it to continue.", "2024-02-02")
    assert hits == [FactHit("phone", "ending 1234", "We sent a code to your phone number ******1234. Enter it to continue.", "2024-02-02")]


def test_address_line_after_cue():
    text = "Thanks for your order!\nShipping address:\nKinnari S\n12 High St\nLondon SW1A 1AA\nUnited Kingdom\n"
    hits = extract_facts(text, "2024-03-03")
    assert [h.fact for h in hits] == ["address"]
    assert hits[0].value == "London SW1A 1AA"


def test_no_false_positives_on_marketing_copy():
    text = "Get 20% off with code SAVE20 on orders over $50. Free delivery on 100000 items!"
    assert extract_facts(text, "2024-04-04") == []


def test_evidence_is_capped():
    text = "card ending 1111 " + "x" * 500
    hits = extract_facts(text, "2024-05-05")
    assert len(hits[0].evidence) <= EVIDENCE_WIDTH


def test_trigger_words_are_whole_words():
    assert extract_facts("Your cardio class starts, ending in 1234 minutes.", "2024-06-06") == []
    assert extract_facts("We encode your favorite number 123456 for stats.", "2024-06-06") == []
    hits = extract_facts("Your card ending 1234", "2024-06-06")
    assert hits[0].fact == "card" and hits[0].value == "ending 1234"


def test_address_prefers_town_postcode_line_over_street_number():
    text = "Thanks for your order!\nShipping address:\n1234 Main St\nSpringfield IL 62704\nUSA\n"
    hits = extract_facts(text, "2024-07-07")
    assert hits[0].fact == "address" and hits[0].value == "Springfield IL 62704"


def test_address_postcode_first_line():
    text = "Shipping address:\n1010 Wien\nAustria\n"
    hits = extract_facts(text, "2024-08-08")
    assert hits[0].fact == "address" and hits[0].value == "1010 Wien"


def test_address_trailing_four_digit_postcode():
    text = "Shipping address:\n12 Smith St\nSydney NSW 2000\nAustralia\n"
    hits = extract_facts(text, "2024-08-09")
    assert hits[0].fact == "address" and hits[0].value == "Sydney NSW 2000"


def test_merge_confidence_by_distinct_dates():
    hits = [
        FactHit("card", "ending 4421", "e1", "2024-01-01"),
        FactHit("card", "ending 4421", "e2", "2024-06-01"),
        FactHit("card", "ending 9999", "e3", "2024-06-01"),
        FactHit("phone", "ending 1234", "e4", "2024-06-01"),
        FactHit("phone", "ending 1234", "e5", "2024-06-01"),
    ]
    facts = {(f.fact, f.value): f for f in merge_facts(hits)}
    assert facts[("card", "ending 4421")].confidence == "high"
    assert facts[("card", "ending 4421")].evidence == "e2" and facts[("card", "ending 4421")].seen == "2024-06-01"
    assert facts[("card", "ending 9999")].confidence == "medium"
    assert facts[("phone", "ending 1234")].confidence == "medium"   # same date twice
