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
_HEADCOUNT_RANK: dict[str, int] = {k: i for i, k in enumerate(_HEADCOUNT_BANDS)}

_SCORE_COLOR = {
    "good": "#2d9e2d",
    "maybe": "#b8860b",
    "discard": "#cc3333",
    "enrich": "#2255cc",
}


def _load_listing_index(vault: Vault) -> tuple[dict[str, str], dict[str, str]]:
    """Return (siren -> matched_city, naf_code -> naf_label) from listing.jsonl."""
    listing_path = vault.root / "listing.jsonl"
    if not listing_path.exists():
        return {}, {}
    cities: dict[str, str] = {}
    naf_labels: dict[str, str] = {}
    for line in listing_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            siren = rec.get("siren", "")
            city = rec.get("matched_city", "")
            if siren and city:
                cities[siren] = city
            code = rec.get("naf_code", "")
            label = rec.get("naf_label", "")
            if code and label:
                naf_labels[code] = label
        except Exception:
            pass
    return cities, naf_labels


def _parse_domaine(first_line: str) -> str:
    m = re.search(r"\*\*Domaine\*\*:\s*([^·\n]+)", first_line)
    if m:
        return m.group(1).strip().rstrip("·").strip()
    return ""


def _load_rows(vault: Vault) -> list[dict]:  # type: ignore[type-arg]
    nodes_dir = vault.root / "nodes"
    if not nodes_dir.exists():
        return []

    listing_index, naf_label_index = _load_listing_index(vault)

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
        size_rank = _HEADCOUNT_RANK.get(size_code, 99)

        summary_text = sum_data.get("summary", "")
        first_line = summary_text.split("\n")[0] if summary_text else ""
        snippet = re.sub(r"\*\*[^*]+\*\*:\s*", "", first_line).strip()
        domaine = _parse_domaine(first_line)

        siren = siren_data.get("siren", "")
        city = siege.get("libelle_commune", "") or siege.get("commune", "")
        naf = siren_data.get("activite_principale", "")
        naf_label = naf_label_index.get(naf, "")
        matched_city = listing_index.get(siren, "")
        categorie = siren_data.get("categorie_entreprise", "")

        rows.append({
            "node_id": node_id,
            "name": name,
            "size": size,
            "size_rank": size_rank,
            "snippet": snippet,
            "score": eval_data.get("score", ""),
            "fit": eval_data.get("fit", ""),
            "reaction": review_data.get("reaction", ""),
            "summary": summary_text,
            "dealbreakers": eval_data.get("dealbreakers", []),
            "siren": siren,
            "naf": naf,
            "naf_label": naf_label,
            "city": city,
            "domaine": domaine,
            "matched_city": matched_city,
            "categorie": categorie,
        })

    return rows


_CSS_MAIN = """
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; font-family: sans-serif; background: #f9f9f9; color: #222; }
#layout { display: flex; height: 100vh; }
#left { width: 55%; overflow-y: auto; border-right: 1px solid #ddd; padding: 1rem; }
#right { flex: 1; }
#right iframe { width: 100%; height: 100%; border: none; }
h1 { font-size: 1.2rem; margin: 0 0 0.5rem; }
#filters { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; }
#filters input, #filters select { font-size: 0.8rem; padding: 0.25rem 0.4rem; border: 1px solid #ccc; border-radius: 3px; }
#filters input { width: 10rem; }
table { border-collapse: collapse; width: 100%; background: #fff; }
th, td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid #e0e0e0; font-size: 0.85rem; }
th { background: #f0f0f0; user-select: none; white-space: nowrap; }
th.sortable { cursor: pointer; }
th.sortable:hover { background: #e4e4e4; }
th.sort-asc::after { content: ' ↑'; }
th.sort-desc::after { content: ' ↓'; }
tr { cursor: pointer; }
tr:hover { background: #eef4ff; }
tr.active { background: #ddeeff; }
tr.hidden { display: none; }
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

    # Collect distinct values for filter dropdowns
    all_scores = sorted({r["score"] for r in rows if r["score"]})
    all_reactions = sorted({r["reaction"] for r in rows if r["reaction"]})
    all_batches = sorted({r["matched_city"] for r in rows if r["matched_city"]})
    all_categories = sorted({r["categorie"] for r in rows if r["categorie"]})
    all_nafs = sorted({(r["naf"], r["naf_label"]) for r in rows if r["naf"]})

    def opt(val: str) -> str:
        return f'<option value="{escape(val)}">{escape(val)}</option>'

    score_opts = "".join(opt(v) for v in all_scores)
    reaction_opts = "".join(opt(v) for v in all_reactions)
    batch_opts = "".join(opt(v) for v in all_batches)
    categorie_opts = "".join(opt(v) for v in all_categories)
    naf_opts = "".join(
        f'<option value="{escape(code)}">{escape(code)}{" — " + escape(label) if label else ""}</option>'
        for code, label in all_nafs
    )

    # score rank used both for default sort and as a data attribute
    _SCORE_RANK = {"good": 0, "maybe": 1, "enrich": 2, "discard": 3}

    tbody = ""
    for r in rows:
        score = r["score"]
        color = _SCORE_COLOR.get(score, "#888")
        score_cell = f'<span class="score" style="color:{color}">{escape(score)}</span>' if score else '<span class="dim">—</span>'
        reaction_val = r["reaction"]
        reaction_disp = escape(reaction_val) if reaction_val else '<span class="dim">—</span>'
        name = escape(r["name"] or r["node_id"])
        size = escape(r["size"]) or '<span class="dim">—</span>'
        city = escape(r["city"]) or '<span class="dim">—</span>'
        naf = escape(r["naf"]) or '<span class="dim">—</span>'
        domaine = escape(r["domaine"]) or '<span class="dim">—</span>'
        matched_city_val = r["matched_city"]
        matched_city = escape(matched_city_val) or '<span class="dim">—</span>'
        categorie_val = r["categorie"]
        categorie = escape(categorie_val) or '<span class="dim">—</span>'
        node_url = f"/node/{escape(r['node_id'])}"
        score_rank = _SCORE_RANK.get(score, 9)
        name_lower = (r["name"] or r["node_id"]).lower()
        naf_val = r["naf"]
        tbody += (
            f'<tr onclick="show(\'{node_url}\', this)"'
            f' data-score="{escape(score)}"'
            f' data-score-rank="{score_rank}"'
            f' data-size-rank="{r["size_rank"]}"'
            f' data-reaction="{escape(reaction_val)}"'
            f' data-batch="{escape(matched_city_val)}"'
            f' data-name="{escape(name_lower)}"'
            f' data-city="{escape((r["city"] or "").lower())}"'
            f' data-domaine="{escape((r["domaine"] or "").lower())}"'
            f' data-categorie="{escape(categorie_val)}"'
            f' data-naf="{escape(naf_val)}"'
            f' data-node-id="{escape(r["node_id"])}"'
            f'>'
            f"<td>{name}</td>"
            f"<td>{size}</td>"
            f"<td>{score_cell}</td>"
            f"<td>{reaction_disp}</td>"
            f"<td>{city}</td>"
            f"<td>{naf}</td>"
            f"<td>{domaine}</td>"
            f"<td>{matched_city}</td>"
            f"<td>{categorie}</td>"
            f"</tr>\n"
        )

    return f"""<!doctype html>
<html><head><meta charset=utf-8><title>ANPE nodes</title>
<style>{_CSS_MAIN}</style></head>
<body>
<div id="layout">
  <div id="left">
    <h1>Nodes (<span id="count">{len(rows)}</span>)</h1>
    <div id="filters">
      <input id="f-name" type="search" placeholder="Search name…" oninput="applyFilters()">
      <select id="f-score" onchange="applyFilters()">
        <option value="">All scores</option>{score_opts}
      </select>
      <select id="f-reaction" onchange="applyFilters()">
        <option value="">All reactions</option>{reaction_opts}
      </select>
      <select id="f-batch" onchange="applyFilters()">
        <option value="">All batches</option>{batch_opts}
      </select>
      <select id="f-categorie" onchange="applyFilters()">
        <option value="">All catégories</option>{categorie_opts}
      </select>
      <select id="f-naf" onchange="applyFilters()">
        <option value="">All NAF</option>{naf_opts}
      </select>
    </div>
    <table id="main-table">
    <thead><tr>
      <th class="sortable" data-col="name">Company</th>
      <th class="sortable" data-col="size-rank">Size</th>
      <th class="sortable" data-col="score-rank">Score</th>
      <th class="sortable" data-col="reaction">Reaction</th>
      <th class="sortable" data-col="city">City</th>
      <th>NAF</th>
      <th class="sortable" data-col="domaine">Domaine</th>
      <th class="sortable" data-col="batch">Batch</th>
      <th class="sortable" data-col="categorie">Catégorie</th>
    </tr></thead>
    <tbody id="tbody">{tbody}</tbody>
    </table>
  </div>
  <div id="right"><iframe name="detail" src="about:blank"></iframe></div>
</div>
<script>
// Column index -> data attribute mapping
const COL_DATA = ['name', null, 'score-rank', 'reaction', null, null, null, 'batch'];

let sortCol = 'score-rank';
let sortDir = 1; // 1=asc, -1=desc

function show(url, row) {{
  document.querySelectorAll('tr.active').forEach(r => r.classList.remove('active'));
  row.classList.add('active');
  document.querySelector('iframe').src = url;
}}

function applyFilters() {{
  const name = document.getElementById('f-name').value.toLowerCase();
  const score = document.getElementById('f-score').value;
  const reaction = document.getElementById('f-reaction').value;
  const batch = document.getElementById('f-batch').value;
  const categorie = document.getElementById('f-categorie').value;
  const naf = document.getElementById('f-naf').value;
  let visible = 0;
  document.querySelectorAll('#tbody tr').forEach(tr => {{
    const ok = (
      (!name || tr.dataset.name.includes(name)) &&
      (!score || tr.dataset.score === score) &&
      (!reaction || tr.dataset.reaction === reaction) &&
      (!batch || tr.dataset.batch === batch) &&
      (!categorie || tr.dataset.categorie === categorie) &&
      (!naf || tr.dataset.naf === naf)
    );
    tr.classList.toggle('hidden', !ok);
    if (ok) visible++;
  }});
  document.getElementById('count').textContent = visible;
}}

function sortBy(col) {{
  if (sortCol === col) {{
    sortDir *= -1;
  }} else {{
    sortCol = col;
    sortDir = 1;
  }}
  const tbody = document.getElementById('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const NUMERIC_COLS = new Set(['score-rank', 'size-rank']);
  // dataset API converts hyphenated names to camelCase
  const toCamel = s => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
  const key = toCamel(sortCol);
  rows.sort((a, b) => {{
    let va = a.dataset[key] || '';
    let vb = b.dataset[key] || '';
    if (NUMERIC_COLS.has(sortCol)) {{
      const na = parseInt(va, 10); const nb = parseInt(vb, 10);
      const ra = isNaN(na) ? 99 : na; const rb = isNaN(nb) ? 99 : nb;
      if (ra !== rb) return (ra - rb) * sortDir;
    }} else {{
      const cmp = va.localeCompare(vb);
      if (cmp !== 0) return cmp * sortDir;
    }}
    return (a.dataset.nodeId || '').localeCompare(b.dataset.nodeId || '');
  }});
  rows.forEach(r => tbody.appendChild(r));
  // update header indicators
  document.querySelectorAll('th.sortable').forEach(th => {{
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.col === sortCol) {{
      th.classList.add(sortDir === 1 ? 'sort-asc' : 'sort-desc');
    }}
  }});
}}

// Wire up sortable headers (use col index to pick data attribute)
document.querySelectorAll('th.sortable').forEach((th, _) => {{
  th.addEventListener('click', () => sortBy(th.dataset.col));
}});

// Initial sort indicator
document.querySelectorAll('th.sortable').forEach(th => {{
  if (th.dataset.col === sortCol) th.classList.add('sort-asc');
}});
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
