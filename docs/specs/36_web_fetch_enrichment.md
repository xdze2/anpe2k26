---
status: draft
---

# Web fetch enrichment

The `fetch` tool retrieves full page content from URLs proposed by the LLM during
the summarize step. It is a standard fetch tool in the pipeline — same state machine,
same storage conventions as `ddg` and `siren`.

## Motivation

DDG snippets give enough signal to filter obvious mismatches but are too thin for
confident scoring. The company's about page, a careers page, or a press article gives
the LLM the product description, tech stack, and cultural context that makes a summary
useful for eval.

The LLM already proposes website URLs in `new_targets` during the summarize step.
They are currently dropped because the `fetch` tool is not implemented.

---

## Implementation: `trafilatura`

```python
import trafilatura

def http_fetch(url: str) -> str:
    html = trafilatura.fetch_url(url)
    if html is None:
        raise FetchNotFoundError(url)
    text = trafilatura.extract(html, include_links=False)
    if not text:
        raise FetchNotFoundError(url)
    return text[:20_000]  # cap to avoid oversized context
```

`trafilatura` handles fetch + main-content extraction in one call. Output is clean
prose — no nav, footer, or ads — directly usable as LLM input.

### Expected results by target type

| target | expected outcome |
|---|---|
| Company about page | good — product description, values, team |
| Welcome to the Jungle profile | good — culture, stack, open roles |
| Wikipedia | good — history, funding, acquisitions |
| LinkedIn company page | blocked |
| JS-heavy SPA | empty body → `not_found` |
| Cloudflare-protected | blocked |

---

## Manual fallback: browser extension

For JS-heavy or Cloudflare-protected sites, a Firefox extension captures the
rendered DOM and delivers it to the pipeline. The user browses normally; the
extension fires on demand.

The extension POSTs `(url, html_content)` to a local Flask endpoint. The endpoint:

1. Identifies the target node by matching `url` against `new_targets` across all
   nodes (exact or domain-level match).
2. Saves the content as a raw file in `node/raw_data/`.
3. Appends a `fetch_done` event to `fetch.jsonl`.

The pipeline then picks it up as a normal fetch and runs summarize. Ambiguous URL
matches prompt the user to confirm before writing.

This fallback complements `trafilatura` — most nodes won't need it.
