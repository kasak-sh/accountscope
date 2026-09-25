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
