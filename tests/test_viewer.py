import json
import re

from accountscope.viewer import render_html, write_html
from tests.test_report import DATA


def test_html_embeds_json_and_noscript_table():
    html = render_html(DATA)
    m = re.search(r'<script id="inventory" type="application/json">(.*?)</script>', html, re.S)
    assert m and json.loads(m.group(1)) == DATA
    assert "<noscript>" in html
    assert "Example Bank" in html and "finance" in html
    assert "https://example.com/close" in html


def test_html_has_no_external_resources():
    html = render_html(DATA)
    assert not re.search(r'(src|href)="https?://', html.replace('href="https://example.com/close"', ""))
    assert "<link" not in html


def test_json_embedding_escapes_script_close():
    data = json.loads(json.dumps(DATA))
    data["organisations"][0]["name"] = "Evil <!--<script>alert(1)</script>-->"
    html = render_html(data)
    m = re.search(r'<script id="inventory" type="application/json">(.*?)</script>', html, re.S)
    payload = m.group(1)
    assert "<" not in payload and "&" not in payload
    assert json.loads(payload)["organisations"][0]["name"] == "Evil <!--<script>alert(1)</script>-->"
    assert "</script><script>alert" not in html


def test_write_html(tmp_path):
    out = tmp_path / "accountscope.html"
    write_html(DATA, out)
    assert out.read_text(encoding="utf-8").lstrip().startswith("<!doctype html>")


def test_html_flags_inferred_facts_in_the_holds_tag():
    from tests.test_report import with_inferred_fact

    html = render_html(with_inferred_fact())
    assert '<span class="tag">card ending 4421</span>' in html
    assert '<span class="tag tag-inferred">phone ending 9931 (inferred)</span>' in html
    assert ".tag-inferred{" in html


def test_inferred_facts_are_left_out_of_the_holds_filter():
    """The "holds phone" chip is a claim about what an organisation really has, so an
    inferred fact must not make a row answer it."""
    from tests.test_report import with_inferred_fact

    html = render_html(with_inferred_fact())
    m = re.search(r'<tr data-key="example\.com" data-holds="([^"]*)"', html)
    assert m and m.group(1) == "card"


def test_trusted_facts_still_reach_the_holds_filter():
    html = render_html(DATA)
    m = re.search(r'<tr data-key="example\.com" data-holds="([^"]*)"', html)
    assert m and m.group(1) == "card"
