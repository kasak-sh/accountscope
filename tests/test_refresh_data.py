"""The release-time refresh script is not shipped, but the index it builds is.
Only its pure part is exercised here; nothing in this file touches the network."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import urlparse

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "refresh_data.py"


@pytest.fixture(scope="module")
def refresh():
    spec = importlib.util.spec_from_file_location("refresh_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_url_host_is_not_indexed_when_the_site_lists_its_domains(refresh):
    sites = [
        {"name": "Blogger", "url": "https://support.google.com/blogger/answer/41932",
         "domains": ["blogger.com"], "difficulty": "impossible"},
        {"name": "Bountysource", "url": "https://github.com/bountysource/core/issues/409",
         "domains": ["bountysource.com"], "difficulty": "hard"},
    ]
    index = refresh.index_sites(sites)
    assert index["blogger.com"]["name"] == "Blogger"
    assert index["bountysource.com"]["name"] == "Bountysource"
    assert "google.com" not in index
    assert "github.com" not in index


def test_a_site_without_domains_still_falls_back_to_its_url_host(refresh):
    sites = [{"name": "Example", "url": "https://www.example.com/close", "difficulty": "easy"}]
    index = refresh.index_sites(sites)
    assert index["example.com"]["name"] == "Example"


def test_an_exact_domain_claim_beats_an_earlier_url_host(refresh):
    sites = [
        {"name": "Docs", "url": "https://help.example.com/delete", "difficulty": "hard"},
        {"name": "Example", "url": "https://example.com/account", "domains": ["example.com"],
         "difficulty": "easy"},
    ]
    index = refresh.index_sites(sites)
    assert index["example.com"]["name"] == "Example"


def test_the_first_exact_claim_keeps_the_key(refresh):
    sites = [
        {"name": "First", "url": "https://example.com/a", "domains": ["example.com"], "difficulty": "easy"},
        {"name": "Second", "url": "https://example.com/b", "domains": ["example.com"], "difficulty": "hard"},
    ]
    assert refresh.index_sites(sites)["example.com"]["name"] == "First"


def test_a_subdomain_in_domains_still_maps_to_the_registrable_domain(refresh):
    sites = [{"name": "Shop", "url": "https://shop.example.co.uk/close",
              "domains": ["shop.example.co.uk"], "difficulty": "medium"}]
    index = refresh.index_sites(sites)
    assert index["example.co.uk"]["name"] == "Shop"


def test_versions_file_is_bundled_with_both_dates():
    import json
    from importlib import resources
    versions = json.loads(resources.files("accountscope.data").joinpath("versions.json").read_text(encoding="utf-8"))
    assert set(versions) == {"public_suffix_list", "justdeleteme"}
    for value in versions.values():
        assert len(value) == 10 and value.count("-") == 2


def test_the_bundled_index_does_not_hand_a_parent_domain_to_a_child_site():
    """google.com used to resolve to Blogger and github.com to Bountysource, because
    both articles are hosted on the parent's site. An entry for a key must belong to
    that key: its deletion URL lives on the key's own domain."""
    import json
    from importlib import resources

    from accountscope.orgs import registrable_domain

    index = json.loads(resources.files("accountscope.data").joinpath("justdeleteme.json").read_text(encoding="utf-8"))
    for key in ("google.com", "github.com"):
        entry = index.get(key)
        if entry is None:
            continue
        host = urlparse(entry["url"]).hostname or ""
        assert registrable_domain(host) == key, f"{key} -> {entry['name']} ({entry['url']})"
