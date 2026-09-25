"""One self-contained HTML file: the inventory, grouped, searchable, readable without JavaScript."""
from __future__ import annotations

import html
import json
from pathlib import Path

CSS = """
:root{--ink:#1a1f1e;--muted:#5c6663;--rule:#d6ddd8;--accent:#0e6b60;--soft:#ddefeb;--bg:#f5f7f4;--card:#fff}
@media(prefers-color-scheme:dark){:root{--ink:#e7ece9;--muted:#9ca69f;--rule:#2a3331;--accent:#57bdac;--soft:#163a35;--bg:#111615;--card:#1a2120}}
body{margin:0;padding:24px;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 8px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.meta{color:var(--muted);font-size:13px}.tools{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
input[type=search]{flex:1 1 240px;padding:8px 10px;border:1px solid var(--rule);border-radius:6px;background:var(--card);color:var(--ink)}
.chip{border:1px solid var(--rule);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 11px;font-size:13px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--soft);border-color:var(--accent);color:var(--accent)}
table{width:100%;border-collapse:collapse;background:var(--card);font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.wrap{overflow-x:auto;border:1px solid var(--rule);border-radius:6px}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;background:var(--soft);color:var(--accent);font-size:12px;margin:0 4px 2px 0}
.dim{color:var(--muted)}a{color:var(--accent)}tr[hidden]{display:none}
"""

JS = """
(function(){
var data=JSON.parse(document.getElementById('inventory').textContent);
var rows=[].slice.call(document.querySelectorAll('tr[data-key]'));
var q=document.getElementById('q');var chips=[].slice.call(document.querySelectorAll('.chip'));
var addr=document.getElementById('addr');
function apply(){
  var text=q.value.toLowerCase();var active=chips.filter(function(c){return c.getAttribute('aria-pressed')==='true'}).map(function(c){return c.dataset.filter});
  var a=addr.value;
  rows.forEach(function(r){
    var ok=!text||r.textContent.toLowerCase().indexOf(text)>=0;
    if(ok&&active.indexOf('card')>=0)ok=r.dataset.holds.indexOf('card')>=0;
    if(ok&&active.indexOf('phone')>=0)ok=r.dataset.holds.indexOf('phone')>=0;
    if(ok&&active.indexOf('marketing')>=0)ok=r.dataset.marketing==='1';
    if(ok&&a)ok=r.dataset.writes.split('|').indexOf(a)>=0;
    r.hidden=!ok;
  });
  document.querySelectorAll('section').forEach(function(s){s.hidden=!s.querySelector('tr[data-key]:not([hidden])')});
}
q.addEventListener('input',apply);addr.addEventListener('change',apply);
chips.forEach(function(c){c.addEventListener('click',function(){c.setAttribute('aria-pressed',c.getAttribute('aria-pressed')==='true'?'false':'true');apply()})});
document.getElementById('tools').hidden=false;
})();
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _rows(orgs: list[dict]) -> str:
    out = []
    for o in orgs:
        holds = " ".join(f'<span class="tag">{_esc(h["fact"])} {_esc(h["value"])}</span>' for h in o["holds"])
        writes = "<br>".join(f'{_esc(w["address"])} <span class="dim">{_esc(w["last"] or "undated")}</span>' for w in o["writes_to"])
        delete = o.get("delete") or {}
        link = f'<a href="{_esc(delete["url"])}" rel="noopener">delete ({_esc(delete.get("difficulty", ""))})</a>' if delete.get("url") else '<span class="dim">-</span>'
        types = ", ".join(f"{_esc(t)} {n}" for t, n in o["types"].items())
        out.append(
            f'<tr data-key="{_esc(o["key"])}" data-holds="{_esc(" ".join(h["fact"] for h in o["holds"]))}" '
            f'data-marketing="{1 if o["marketing_only"] else 0}" data-writes="{_esc("|".join(w["address"] for w in o["writes_to"]))}">'
            f'<td><strong>{_esc(o["name"])}</strong><br><span class="dim">{_esc(o["key"])}</span></td>'
            f'<td>{writes}</td><td>{holds or "<span class=\"dim\">-</span>"}</td>'
            f'<td class="dim">{types}</td><td>{_esc(o["first_seen"] or "")} to {_esc(o["last_seen"] or "")}</td><td>{link}</td></tr>'
        )
    return "\n".join(out)


def _sections(orgs: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for o in orgs:
        groups.setdefault(o["category"], []).append(o)
    order = ["finance", "government", "utilities", "health", "telecom", "travel", "work", "social", "shopping", "other"]
    parts = []
    for cat in order:
        if cat not in groups:
            continue
        parts.append(
            f'<section><h2>{_esc(cat)} <span class="dim">({len(groups[cat])})</span></h2><div class="wrap"><table>'
            '<thead><tr><th>Organisation</th><th>Writes to</th><th>Holds</th><th>Mail</th><th>Seen</th><th>Delete</th></tr></thead>'
            f'<tbody>{_rows(groups[cat])}</tbody></table></div></section>'
        )
    return "\n".join(parts)


def render_html(data: dict) -> str:
    payload = (json.dumps(data, ensure_ascii=False)
               .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))
    self_options = "".join(f'<option value="{_esc(s["address"])}">{_esc(s["address"])}</option>' for s in data["self"])
    src = data["source"]
    body_sections = _sections(data["organisations"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>accountscope inventory</title><style>{CSS}</style></head>
<body>
<h1>Your accounts</h1>
<p class="meta">{len(data["organisations"])} organisations from {_esc(src.get("path", ""))} · {src.get("messages", 0):,} messages · generated {_esc(data.get("generated_at", ""))}</p>
<div class="tools" id="tools" hidden>
  <input id="q" type="search" placeholder="Search organisations" aria-label="Search">
  <select id="addr" aria-label="Writes to"><option value="">any of my addresses</option>{self_options}</select>
  <button class="chip" data-filter="card" aria-pressed="false" type="button">holds card</button>
  <button class="chip" data-filter="phone" aria-pressed="false" type="button">holds phone</button>
  <button class="chip" data-filter="marketing" aria-pressed="false" type="button">newsletters only</button>
</div>
<noscript><p class="meta">Scripting is off; the full table is below.</p></noscript>
{body_sections}
<script id="inventory" type="application/json">{payload}</script>
<script>{JS}</script>
</body></html>
"""


def write_html(data: dict, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render_html(data), encoding="utf-8")
    tmp.replace(path)
