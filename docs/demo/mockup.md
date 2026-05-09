---
status: draft
---

# Demo mockup — target end-state

A walkthrough showing what the finished tool feels like to use. Two
purposes:

- **A target.** Pin down what we are building toward, concretely enough to
  notice when the real CLI drifts from it.
- **An explainer.** Something to show a person in 90 seconds that
  communicates the idea (discovery, not search) and the loop (enrich,
  surface, react, sharpen).

The mockup is **CLI-only**. The exploration loop is already CLI-shaped
(`scan | put | run`, `loop`, `review`); a TUI would be a different app.
Match the tool we're shipping.

The gif is generated from a [vhs](https://github.com/charmbracelet/vhs)
script (`demo.tape`, below). Source-controlled, deterministic, regenerates
on demand — no re-acting the session each time the demo changes.

---

## The story in four beats

1. **Cold start.** Tool knows nothing. User has a profile (a few lines of
   markdown about what they want). Bootstrap pulls thousands of candidates
   from SIRENE.
2. **Autonomous enrichment.** `anpe loop` runs with a budget, narrows
   thousands → dozens through cheap fetches and LLM evaluation.
3. **Human moment.** A handful surface for review. User reacts in plain
   English. Reactions feed the profile.
4. **Sharpening.** Next loop pass weighs candidates against the *updated*
   profile. The funnel gets visibly tighter, more relevant.

The fourth beat is the payoff. Without it the demo is just "watch a
pipeline run."

---

## Frame 1 — cold start, profile in hand

```
$ cat user_profile.md
# What I'm looking for

- Small AI / data-focused company (5-50 people)
- Bordeaux or fully remote
- Ideally working on something concrete, not pure research
- Comfortable with Python and ML; open to other stacks

$ anpe loop --budget mistral=20 --budget ddg=200
```

A short profile. Vague on purpose — the loop will sharpen it.

---

## Frame 2 — bootstrap surfacing thousands

```
[bootstrap]   profile_hash=a1f3...   pulling SIRENE listing
              ████████████████████████████████  3,847 companies
              filtered: NAF 62.* (IT services), Gironde + remote-friendly

[fetch_siren] ◐ 50 / 3847   ─ rate-limited at 1 req/s, will resume
[fetch_ddg]   ◐ 50 / 50     ─ enriching what siren produced
[summarize]   ◐ 50 / 50     ─ Mistral, 2s/call

  budget remaining: mistral 20 → 0   ddg 200 → 150   stopping.
```

The user sees scale: 3,847 candidates, narrowed by NAF + geography to a
working set, enriched within a budget. No claim of "I evaluated all 3,847
intelligently" — the budget is honest.

---

## Frame 3 — the funnel after one pass

```
$ anpe jobs status

  step              pending   done   discarded
  ─────────────────────────────────────────────
  bootstrap            –        1         –
  fetch_siren        3797       50         –
  fetch_ddg            –        50         –
  summarize_ddg        –        47         3   ← 3 not relevant
  eval                 –        47         –
  review              23        –         24   ← 24 LLM-discarded

  budget spent:  mistral 20/20   ddg 50/200
```

47 enriched, 24 LLM-discarded as bad fits, 23 surfaced for review. The
funnel is real and visible.

---

## Frame 4 — review: the human moment

```
$ anpe prospect review --score=good --score=maybe

──────────── Vinili Studio  •  Bordeaux  •  ~12 people ───────────

  AI-assisted wine label design. Small team mixing creative direction
  with diffusion-model fine-tuning for niche typography. Recently
  partnered with two AOC cooperatives in the Médoc.

  score: good   fit: small team, AI applied to a concrete domain, local
  next_targets: vinili-studio.fr, linkedin.com/company/vinili-studio

  > interesting — the wine industry angle is a surprise but I like
    that they're applying ML to something real. flag for outreach.

──────────── Pelagia Data  •  remote (Bordeaux HQ)  •  ~8 people ─────

  Marine biology data pipelines for IFREMER. Small Python shop, mostly
  geospatial work. Recent hire from CNRS.

  score: good   fit: small, remote, applied data work
  next_targets: pelagia-data.com

  > pass. data plumbing only, no ML.

──────────── DéciTech  •  Bordeaux  •  ~30 people ──────────────────

  Decision-support consulting for retail logistics. Some ML, mostly
  classical optimization.

  score: maybe
  next_targets: decitech.fr/about

  > too consulting-shaped, not interested

──────────── Loupy.ai  •  remote  •  ~6 people ─────────────────────

  ...

  3 reactions saved.  20 remaining.   q to stop.
```

This is the demo's heart. Three things to notice:

- **The "wine industry" company.** This is the surprise the vision doc
  promises: a thing the user would never have searched for, surfaced by
  the brute-force-then-triage approach.
- **Reactions are plain English.** No clicks, no checkboxes. The user
  writes what they actually think; the LLM digests it later.
- **The score is visible but not authoritative.** "good" doesn't mean the
  user agrees. The user's verdict is what gets recorded.

---

## Frame 5 — profile sharpens

```
$ anpe profile update

  Reading 3 new reactions.
  Synthesizing diff against current profile via Mistral...

  ── proposed additions ──────────────────────────────────────────
  + Strong preference for ML applied to a *non-tech* domain (wine,
    biology, art) over generic data-pipeline work
  + Explicit dislike: consulting-shaped engagements, even when the
    underlying tech matches
  + "Surprising" sector matches are welcome — the user reacted
    positively to an unexpected industry pairing

  ── proposed removals ───────────────────────────────────────────
  – (none)

  Apply? [y/N] y

  Profile written: user_profile_20260509T1815.md
  ── 3 reactions consolidated. 47 evals are now stale.
```

The user sees what the LLM extracted from three short comments — and can
veto. The new profile is a snapshot file (no overwrite), and the *47
existing evals are flagged stale* because the profile they were scored
against has been superseded.

---

## Frame 6 — second pass, visibly tighter

```
$ anpe loop --budget mistral=20

[scan eval]      47 stale (profile updated)
[run  eval]      ████████████████████████████████  20/47 done
                 7 promoted to 'good'    9 demoted to 'discard'    4 'maybe'

  Funnel after 2 passes:

  surfaced now (good + new):  ▮▮▮▮▮▮▮  7
  surfaced before (good):     ▮▮▮▮▮▮▮▮▮▮▮▮  12
  consistent across passes:   ▮▮▮▮▮  5

  budget spent: mistral 20/20.   27 evals remain stale (run again to flush).
```

The before/after is the explanation. After one round of feedback, the
ranking is no longer the same — companies that *seemed* like a fit before
the user's reactions are now correctly demoted; the new "good" set
includes more of the surprising-domain matches the user signaled they
liked.

---

## What the demo is *not* showing

Honesty about the boundaries makes the demo more credible:

- No claim of finding the "best" company — the system surfaces, doesn't
  rank-all.
- No claim that 47 evals is enough to find the right job — this is one
  session of an ongoing exploration. The vision doc is explicit about
  this.
- No automation past the human review step. The user always reads and
  reacts; the LLM never decides who to contact.

---

## Generating the gif

[vhs](https://github.com/charmbracelet/vhs) takes a `.tape` script and
produces a gif (or mp4) deterministically. Below is `demo.tape` — checked
in alongside this file. To regenerate:

```bash
brew install vhs            # or: go install github.com/charmbracelet/vhs@latest
vhs docs/demo/demo.tape     # produces docs/demo/demo.gif
```

The script uses `Type "..."` for visible typing and `Sleep` for pacing.
Output file path, terminal size, theme, and font are set at the top.

The actual `anpe` calls in the script run against a **fixture vault**
(`docs/demo/fixture/`) so the demo is reproducible and does not hit
SIRENE / DDG / Mistral every time. Building that fixture is its own
small task — see "Building the fixture" below.

### Why vhs over asciinema

`asciinema rec` captures a real session — good for "look what happened
just now," bad for a demo you re-record after every UI tweak. `vhs` is
declarative: edit the script, regenerate. Source-controlled,
deterministic, no flubbed typing.

### Building the fixture

The demo needs a stable dataset to play against. One-time setup:

1. Run a real `anpe loop` against a real (small) profile. Capture
   `user_vault/queue.db` and the `user_vault/<node>/...` artifacts.
2. Hand-edit a few summaries / evals to make the surfaced companies
   tell a clear story (the wine company, etc.). The vault is plain
   files; this is just text editing.
3. Save the result under `docs/demo/fixture/`. Point the demo's
   `ANPE_VAULT` env var at it.

Then `demo.tape` runs `anpe` commands against the fixture, so the output
is reproducible across machines.

---

## Status

This file is a **target**, not a description of what works today.
Specifically, the following demo elements are not yet implemented:

- `anpe loop` with `--budget mistral=N --budget ddg=N` (todo P1)
- The pretty `[step] ◐ N/M` progress display (no equivalent today)
- `anpe profile update` proposing a diff (today: prints the prompt only)
- `anpe prospect review --score=good --score=maybe` (review step exists,
  CLI not wired)

When the real CLI catches up, the mockup gets re-rendered as the actual
gif. Until then it lives here as a goalpost.
