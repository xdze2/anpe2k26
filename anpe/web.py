"""Simple Flask web view for the node vault."""

from __future__ import annotations

import json
import re
from pathlib import Path

from flask import Flask, abort
from markupsafe import escape

from anpe.engine.vault import Vault

app = Flask(__name__)

_HEADCOUNT_BANDS: dict[str, str] = {
    "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
    "31": "200-249", "32": "250-499", "41": "500-999",
    "42": "1000-1999", "51": "2000-4999", "52": "5000-9999", "53": "10000+",
}

_SCORE_COLOR = {
    "good": "#2d9e2d",
    "maybe": "#b8860b",
    "discard": "#cc3333",
    "enrich": "#2255cc",
}


def _load_listing_index(vault: Vault) -> dict[str, str]:
    """Return siren -> matched_city from listing.jsonl."""
    listing_path = vault.root / "listing.jsonl"
    if not listing_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in listing_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            siren = rec.get("siren", "")
            city = rec.get("matched_city", "")
            if siren and city:
                result[siren] = city
        except Exception:
            pass
    return result


def _parse_domaine(first_line: str) -> str:
    m = re.search(r"\*\*Domaine\*\*:\s*([^·\n]+)", first_line)
    if m:
        return m.group(1).strip().rstrip("·").strip()
    return ""


def _load_rows(vault: Vault) -> list[dict]:  # type: ignore[type-arg]
    nodes_dir = vault.root / "nodes"
    if not nodes_dir.exists():
        return []

    listing_index = _load_listing_index(vault)

    rows = []
    for node_dir in sorted(nodes_dir.iterdir()):
        if not node_dir.is_dir():
            continue
        node_id = node_dir.name

        summary_paths = list(node_dir.glob("summarize_ddg_*.json"))
        if not summary_paths:
            continue
        try:
            sum_data = json.loads(summary_paths[0].read_bytes())
        except Exception:
            continue
        if sum_data.get("status") != "ok":
            continue

        siren_data: dict = {}  # type: ignore[type-arg]
        siren_paths = list(node_dir.glob("fetch_siren_*.json"))
        if siren_paths:
            try:
                siren_data = json.loads(siren_paths[0].read_bytes())
            except Exception:
                pass

        eval_data: dict = {}  # type: ignore[type-arg]
        eval_paths = list(node_dir.glob("eval_*.json"))
        if eval_paths:
            try:
                eval_data = json.loads(eval_paths[0].read_bytes())
            except Exception:
                pass

        review_data: dict = {}  # type: ignore[type-arg]
        review_paths = list(node_dir.glob("review_*.json"))
        if review_paths:
            try:
                review_data = json.loads(review_paths[0].read_bytes())
            except Exception:
                pass

        siege = siren_data.get("siege", {})
        nom_legal = siren_data.get("nom_complet", "")
        name = siege.get("nom_commercial") or nom_legal or node_id
        size_code = siren_data.get("tranche_effectif_salarie", "")
        size = _HEADCOUNT_BANDS.get(size_code, size_code) if size_code else ""

        summary_text = sum_data.get("summary", "")
        first_line = summary_text.split("\n")[0] if summary_text else ""
        snippet = re.sub(r"\*\*[^*]+\*\*:\s*", "", first_line).strip()
        domaine = _parse_domaine(first_line)

        siren = siren_data.get("siren", "")
        city = siege.get("libelle_commune", "") or siege.get("commune", "")
        naf = siren_data.get("activite_principale", "")
        matched_city = listing_index.get(siren, "")

        rows.append({
            "node_id": node_id,
            "name": name,
            "size": size,
            "snippet": snippet,
            "score": eval_data.get("score", ""),
            "fit": eval_data.get("fit", ""),
            "reaction": review_data.get("reaction", ""),
            "summary": summary_text,
            "dealbreakers": eval_data.get("dealbreakers", []),
            "siren": siren,
            "naf": naf,
            "city": city,
            "domaine": domaine,
            "matched_city": matched_city,
        })

    return rows


_CSS_MAIN = """
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; font-family: sans-serif; background: #f9f9f9; color: #222; }
#layout { display: flex; height: 100vh; }
#left { width: 55%; overflow-y: auto; border-right: 1px solid #ddd; padding: 1rem; }
#right { flex: 1; }
#right iframe { width: 100%; height: 100%; border: none; }
h1 { font-size: 1.2rem; margin: 0 0 0.75rem; }
table { border-collapse: collapse; width: 100%; background: #fff; }
th, td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid #e0e0e0; font-size: 0.85rem; }
th { background: #f0f0f0; }
tr { cursor: pointer; }
tr:hover { background: #eef4ff; }
tr.active { background: #ddeeff; }
.score { font-weight: bold; }
.dim { color: #888; }
"""

_CSS_DETAIL = """
body { font-family: sans-serif; margin: 1.5rem; background: #fff; color: #222; }
h1 { font-size: 1.2rem; margin-bottom: 0.5rem; }
h2 { font-size: 1rem; margin-top: 1.2rem; }
.score { font-weight: bold; }
.dim { color: #888; font-size: 0.85rem; }
pre { white-space: pre-wrap; background: #f4f4f4; padding: 1rem; border-radius: 4px; font-size: 0.85rem; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.2rem 1rem; font-size: 0.85rem; }
dt { font-weight: bold; color: #555; }
ul { margin: 0.3rem 0; padding-left: 1.2rem; }
"""


@app.route("/")
def index() -> str:
    vault = Vault()
    rows = _load_rows(vault)

    rows.sort(key=lambda r: (
        {"good": 0, "maybe": 1, "enrich": 2, "discard": 3, "": 4}.get(r["score"], 4),
        r["node_id"],
    ))

    tbody = ""
    for r in rows:
        score = r["score"]
        color = _SCORE_COLOR.get(score, "#888")
        score_cell = f'<span class="score" style="color:{color}">{escape(score)}</span>' if score else '<span class="dim">—</span>'
        reaction = escape(r["reaction"]) or ""
        name = escape(r["name"] or r["node_id"])
        size = escape(r["size"]) or '<span class="dim">—</span>'
        city = escape(r["city"]) or '<span class="dim">—</span>'
        naf = escape(r["naf"]) or '<span class="dim">—</span>'
        domaine = escape(r["domaine"]) or '<span class="dim">—</span>'
        matched_city = escape(r["matched_city"]) or '<span class="dim">—</span>'
        node_url = f"/node/{escape(r['node_id'])}"
        tbody += (
            f'<tr onclick="show(\'{node_url}\', this)">'
            f"<td>{name}</td>"
            f"<td>{size}</td>"
            f"<td>{score_cell}</td>"
            f"<td>{reaction}</td>"
            f"<td>{city}</td>"
            f"<td>{naf}</td>"
            f"<td>{domaine}</td>"
            f"<td>{matched_city}</td>"
            f"</tr>\n"
        )

    return f"""<!doctype html>
<html><head><meta charset=utf-8><title>ANPE nodes</title>
<style>{_CSS_MAIN}</style></head>
<body>
<div id="layout">
  <div id="left">
    <h1>Nodes ({len(rows)})</h1>
    <table>
    <thead><tr><th>Company</th><th>Size</th><th>Score</th><th>Reaction</th><th>City</th><th>NAF</th><th>Domaine</th><th>Batch</th></tr></thead>
    <tbody>{tbody}</tbody>
    </table>
  </div>
  <div id="right"><iframe name="detail" src="about:blank"></iframe></div>
</div>
<script>
function show(url, row) {{
  document.querySelectorAll('tr.active').forEach(r => r.classList.remove('active'));
  row.classList.add('active');
  document.querySelector('iframe').src = url;
}}
</script>
</body></html>"""


@app.route("/node/<node_id>")
def node_detail(node_id: str) -> str:
    vault = Vault()
    nodes_dir = vault.root / "nodes"
    node_dir = nodes_dir / node_id

    if not node_dir.exists():
        abort(404)

    # Load all available data
    sum_data: dict = {}  # type: ignore[type-arg]
    summary_paths = list(node_dir.glob("summarize_ddg_*.json"))
    if summary_paths:
        try:
            sum_data = json.loads(summary_paths[0].read_bytes())
        except Exception:
            pass

    siren_data: dict = {}  # type: ignore[type-arg]
    siren_paths = list(node_dir.glob("fetch_siren_*.json"))
    if siren_paths:
        try:
            siren_data = json.loads(siren_paths[0].read_bytes())
        except Exception:
            pass

    eval_data: dict = {}  # type: ignore[type-arg]
    eval_paths = list(node_dir.glob("eval_*.json"))
    if eval_paths:
        try:
            eval_data = json.loads(eval_paths[0].read_bytes())
        except Exception:
            pass

    siege = siren_data.get("siege", {})
    nom_legal = siren_data.get("nom_complet", "")
    name = siege.get("nom_commercial") or nom_legal or node_id
    size_code = siren_data.get("tranche_effectif_salarie", "")
    size = _HEADCOUNT_BANDS.get(size_code, size_code) if size_code else ""

    score = eval_data.get("score", "")
    color = _SCORE_COLOR.get(score, "#888")
    score_html = f'<span class="score" style="color:{color}">{escape(score)}</span>' if score else ""

    meta_rows = ""
    for label, val in [
        ("SIREN", siren_data.get("siren", "")),
        ("NAF", siren_data.get("activite_principale", "")),
        ("Taille", size),
        ("Ville", siege.get("libelle_commune", "") or siege.get("commune", "")),
        ("Catégorie", siren_data.get("categorie_entreprise", "")),
    ]:
        if val:
            meta_rows += f"<dt>{escape(label)}</dt><dd>{escape(val)}</dd>"

    targets_html = ""
    new_targets = sum_data.get("new_targets", [])
    if new_targets:
        items = "".join(
            f'<li><span class="dim">{escape(t["tool"])}</span> '
            f'<a href="{escape(t["target"])}" target="_blank">{escape(t["target"])}</a></li>'
            for t in new_targets
        )
        targets_html = f"<h2>Next targets</h2><ul>{items}</ul>"

    summary_html = ""
    summary_text = sum_data.get("summary", "")
    if summary_text:
        summary_html = f"<h2>Summary</h2><pre>{escape(summary_text)}</pre>"

    eval_html = ""
    if eval_data:
        fit = escape(eval_data.get("fit", ""))
        dealbreakers = eval_data.get("dealbreakers", [])
        db_html = ""
        if dealbreakers:
            items = "".join(f"<li>{escape(d)}</li>" for d in dealbreakers)
            db_html = f"<p><strong>Dealbreakers:</strong> <ul>{items}</ul></p>"
        uncertainty = eval_data.get("uncertainty", "")
        unc_html = f"<p><em>Uncertainty: {escape(uncertainty)}</em></p>" if uncertainty else ""
        eval_html = f"<h2>Eval {score_html}</h2><p>{fit}</p>{db_html}{unc_html}"

    return f"""<!doctype html>
<html><head><meta charset=utf-8><title>{escape(name)}</title>
<style>{_CSS_DETAIL}</style></head>
<body>
<h1>{escape(name)}</h1>
<dl>{meta_rows}</dl>
{eval_html}
{targets_html}
{summary_html}
</body></html>"""
