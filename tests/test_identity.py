from accountscope.identity import SelfDetector, canonical


def test_canonical_lowercases_and_strips_plus_tag():
    assert canonical("Me+Shop@Gmail.com") == "me@gmail.com"
    assert canonical("plain@example.org") == "plain@example.org"
    assert canonical("weird+@example.org") == "weird@example.org"


def test_resolve_by_share_and_floor():
    d = SelfDetector()
    for _ in range(300):
        d.add({"me@gmail.com"})
    for _ in range(50):
        d.add({"me+shop@gmail.com", "friend@x.org"})
    for _ in range(5):
        d.add({"rare@y.org"})
    resolved = d.resolve(total_messages=360)
    addresses = {s.address for s in resolved}
    assert "me@gmail.com" in addresses          # 350 >= FLOOR
    assert "friend@x.org" in addresses         # 50/360 = 13.9% >= SHARE
    assert "rare@y.org" not in addresses       # 5/360 = 1.4% < 2%
    me = next(s for s in resolved if s.address == "me@gmail.com")
    assert me.aliases == ["me+shop@gmail.com"]
    assert me.messages == 350
    assert me.declared is False


def test_share_threshold_edge():
    d = SelfDetector()
    for _ in range(1000):
        d.add({"me@gmail.com"})
    for _ in range(19):
        d.add({"almost@x.org"})
    for _ in range(20):
        d.add({"exactly@x.org"})
    addresses = {s.address for s in d.resolve(total_messages=1000)}
    assert "almost@x.org" not in addresses     # 1.9%
    assert "exactly@x.org" in addresses        # 2.0%


def test_me_and_not_me_override_inference():
    d = SelfDetector()
    for _ in range(300):
        d.add({"me@gmail.com", "list@team.org"})
    resolved = d.resolve(total_messages=300, me=["Old@ISP.net"], not_me=["list@team.org"])
    by = {s.address: s for s in resolved}
    assert "list@team.org" not in by
    assert by["old@isp.net"].declared is True and by["old@isp.net"].messages == 0
    assert by["me@gmail.com"].declared is False
