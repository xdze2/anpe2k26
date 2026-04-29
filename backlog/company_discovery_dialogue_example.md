# Company Discovery — Example Dialogue

This document explores the agent workflow through a concrete conversation.
The goal is to surface design questions about what the agent can and cannot do before enrichment exists.

---

## Scenario

User is looking for companies doing AI integration for wine/agriculture near Bordeaux.

---

## Dialogue

**User:** Je cherche des boîtes qui font de l'intégration d'IA pour la viticulture, autour de Bordeaux.

**Agent:** *(calls `naf_search("intégration IA viticulture")`)*

Je vais chercher des entreprises autour de Bordeaux. Pour filtrer par secteur, j'utilise les codes NAF — voici ceux qui correspondent le mieux à ta recherche :

- `62.01Z` — Programmation informatique
- `62.02A` — Conseil en systèmes et logiciels informatiques
- `01.21Z` — Viticulture (pour les domaines viticoles eux-mêmes)

Je pars sur 62.01Z et 62.02A pour cibler les boîtes tech. Tu veux que j'inclue aussi les domaines viticoles (01.21Z) ou on reste sur les prestataires tech ?

---

**User:** Oui reste sur les boîtes tech, rayon 40km.

**Agent:** *(calls `search_companies(city="Bordeaux", radius_km=40, naf_codes=["62.01Z", "62.02A"], page=1)`)*
*(tool geocodes Bordeaux → lat/lon, calls SIRENE /near_point, saves raw results to cache, creates company files for new SIRENs)*

J'ai trouvé 47 entreprises. Voici les 10 premières :

1. **Agritech Solutions** (SIREN 123456789) — 62.01Z — 12 rue des Vignes, Bordeaux
2. **DataVin SAS** (SIREN 234567890) — 62.02A — Mérignac
3. **Inovitis** (SIREN 345678901) — 62.01Z — Pessac
4. **VitiData** (SIREN 456789012) — 62.01Z — Libourne
5. **Agro-SI** (SIREN 567890123) — 62.02A — Agen
6. **NumériCulture** (SIREN 678901234) — 62.01Z — Bordeaux
7. **SudOuest Dev** (SIREN 789012345) — 62.02A — Bordeaux
8. **Terravision** (SIREN 890123456) — 62.01Z — Saint-Émilion
9. **Sysagri** (SIREN 901234567) — 62.02A — Bergerac
10. **Viti-Connect** (SIREN 012345678) — 62.01Z — Bordeaux

**Attention :** ces résultats sont filtrés par code NAF (boîtes informatiques/conseil), pas par activité réelle. Je ne sais pas encore lesquelles travaillent vraiment sur la vigne — il faudrait visiter leurs sites pour le savoir.

Tu veux que je continue à les parcourir, ou tu veux noter certaines comme intéressantes pour les creuser ensuite ?

---

**User:** DataVin ça m'a l'air bien, et Terravision. Les autres pas convaincus. Montre-moi la suite.

**Agent:** *(updates status of SIREN 234567890 → `to_look_at`, SIREN 890123456 → `to_look_at` in their company files)*
*(calls `search_companies(..., page=2)`)*

Noté — DataVin et Terravision passent en `to_look_at`.

Voici les 10 suivantes :

11. **WineIT** (SIREN ...) — 62.01Z — Bordeaux
12. ...

*(etc.)*

---

**User:** Ok j'en ai assez pour l'instant. C'est quoi DataVin exactement ?

**Agent:** *(reads `anpe_data/companies/234567890_datavinsas.md`)*

Voici ce que j'ai sur DataVin :

- **SIREN :** 234567890
- **NAF :** 62.02A — Conseil en systèmes et logiciels informatiques
- **Adresse :** Mérignac (33)
- **Taille :** inconnue (SIRENE ne donne pas la taille pour cette entreprise)

C'est tout ce que j'ai pour l'instant — ces données viennent de SIRENE. Pour savoir ce qu'ils font vraiment, il faudrait récupérer leur site web. Tu veux que je tente ça ?

---

**User:** Oui vas-y.

**Agent:** *(calls `enrich_company("234567890")` — NOT YET IMPLEMENTED)*

> **[Limite actuelle]** L'enrichissement web n'est pas encore implémenté. Je ne peux pas récupérer leur site pour l'instant.

---

## Design questions surfaced by this dialogue

**A. NAF selection step**
The agent must explain the NAF translation to the user — not just do it silently. The user may want to correct it (e.g. include agricultural companies, exclude a code). This suggests the agent should *propose* NAF codes and wait for confirmation before calling SIRENE.

**B. Honest capability framing**
After returning results, the agent must proactively say "these are filtered by sector code, not actual activity." Otherwise the user thinks the 47 companies are all relevant. This belongs in the system prompt or agent instructions.

**C. Pagination UX**
The "show 10, user reacts, show 10 more" loop works, but the agent needs to track page state across turns. With pydantic-ai this means either: passing `page` explicitly each turn, or storing it in the conversation context/tool state.

**D. Inline rating during browsing**
The user rates companies mid-browse ("DataVin looks good"). The agent needs to update files immediately, not at the end. This is a side-effect during a read-heavy flow — make sure `search_companies` and status updates are separate tool calls, not bundled.

**E. Enrichment is the hard blocker for the motivating example**
The dialogue above cannot answer "AI + wine" without `enrich_company`. The browsing flow is useful even without it (surface candidates, let user triage manually), but the design doc should be explicit that phase 1 is candidate discovery, not activity matching.
