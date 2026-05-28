# /embed redesign — in-flight context (2026-05-24)

Handoff doc so this work survives a dropped connection. If you're a
fresh Claude resuming, read this end-to-end before touching
`templates/embed.html`.

## What the user asked

> How do we make the database page feel like the existing site? Right
> now there are categories and you can filter. They stay in smaller
> cards etc — https://www.rhpl.org/research-databases — any ideas?

The current /embed page (Approach A iframe target on the rhpl-studio
test site) renders catalog data but does **not** visually match the
live Wix `/research-databases` page. Goal of this redesign: make
`your-eresources-domain.org/embed` feel like a native section of rhpl.org so
when it's iframed into Wix it disappears into the surrounding chrome.

## Where things stand

### Current `templates/embed.html` (already on disk, 11KB, last edited 13:42)

A first pass landed before the disconnect. What's there now:

- **Two-column layout**: 230px sidebar (category filter list) + flex
  grid of cards. Collapses to single column under 720px (sidebar
  becomes a horizontal chip row).
- **Teal palette** approximated from the live site: `--teal #006978`,
  `--teal-dark #004f5b`, `--teal-bg #f1f7f8`, ink `#1f2933`,
  muted `#5c6b7a`, card border `#c6dbe0`.
- **Cards**: teal-bg fill, rounded 12px, ~220px min-height,
  bold teal title, description, optional "note" line, pill "Visit"
  button, optional "In-library only" badge for `remote_access === 3`.
- **Category sidebar**: list of buttons with name + count, active
  state filled teal with white text, sorted by earliest
  `display_order` then alphabetical, with an "All (N)" entry at top.
- **Skeleton loader**: shimmer placeholder cards while
  `/api/databases.json` loads.
- **Iframe height postMessage**: ResizeObserver on body, posts
  `{source: "rhpl-embed", height: N}` to parent — matches the
  consumer shim in `wix/approach-a-iframe-embed.md`.
- **Referrer**: `no-referrer-when-downgrade` (matches Polaris, see
  [[vendor-referer-whitelists]] memory).

### What's still unverified

The first pass was built from **memory of the live design**, not from
a fresh scrape. The user is right to question whether it actually
matches. Specifically uncertain:

- **Card size.** User said "smaller cards." Current cards are
  ~220px tall × ~half-width-of-1200px = ~580px wide. Live site may
  use ~3-up smaller tiles or a list density rather than 2-up tiles.
- **Filter UI placement.** Live site may use chips along the top
  rather than a left sidebar. (Sidebar was a guess based on
  "categories and you can filter" + the breadth of categories.)
- **Typography.** Live Wix theme has a specific heading font
  (probably Madefor or a Wix default); current code falls back to
  system-ui stack. Need the actual font-family or a close pairing.
- **Color exact match.** Teal values were eyeballed; the live site
  may use a different teal (rhpl.org headers look more
  blue-leaning).
- **"Visit" button vs. card-as-link.** Live site may make the whole
  card clickable with a hover lift rather than a separate CTA pill.
- **Spacing rhythm.** 20px gap, 22px padding — should be checked
  against the live grid.

## What I was doing when the connection dropped

Spawned a background task ("Redesigning /embed as tile-grid + sidebar
filter") that wrote the version of embed.html that's on disk now.
Then user asked the design-match question, I said I'd scrape the live
page, and ran a Playwright probe that timed out on
`wait_until="networkidle"` (60s). Re-attempting with
`domcontentloaded` instead of `networkidle` should fix it — Wix
pages never go idle because of analytics/heartbeat traffic.

See `/tmp/rhpl_design_scrape.py` — that's the probe script. Fix:
change `wait_until="networkidle"` → `wait_until="domcontentloaded"`,
then `pg.wait_for_timeout(4000)` to let Wix hydrate, then run the
evaluate block.

## Edits since first pass

- **2026-05-24 (post-disconnect):** removed the lead intro paragraph
  ("Free online research resources for Rochester Hills Public Library
  cardholders. Inside the library you go straight through; from home
  you sign in once with your library card.") from **both**
  `embed.html` and `listing.html`. Production rhpl.org/research-databases
  doesn't have intro copy, so we don't want it either. The `p.lead` CSS
  rule in embed.html was also removed; `h1.page-title` bottom margin
  bumped from 8px to 28px to preserve spacing above the layout.

## Plan to resume

1. **Re-run the scrape against rhpl.org/research-databases** with the
   `domcontentloaded` fix. Capture:
   - Full-page screenshot (`/tmp/rhpl_research_full.png`)
   - Above-the-fold screenshot
   - Computed CSS samples on body + first card-like container
     (font-family, colors, border-radius, padding)
   - Detected card sizing (width/height of repeated containers)
   - List of filter labels / chips
2. **Compare** the scraped reference to current `embed.html`. Diff:
   - Filter UI shape (chips vs. sidebar)
   - Card dimensions and aspect
   - Color exactness
   - Font stack
   - Whether the whole card is clickable
3. **Iterate on `templates/embed.html`** based on the diff. Keep:
   - The `/api/databases.json` ingest logic
   - The postMessage height beacon
   - The CSP-friendly inline-only CSS (no external fetches)
   - The skeleton loader shape
4. **Re-test in the Wix rhpl-studio iframe** once redeployed. The
   iframe page is `/databases-iframe` on
   `https://vegapromoteweb.wixstudio.com/rhpl-studio` (see
   `wix/approach-a-iframe-embed.md`).

## Constraints to remember

- Don't break the `/api/databases.json` contract. Public-safe fields
  only — never expose `launch_params`, `destination_url`,
  `blocked_patron_code_ids`, or `transfer_type` (see CLAUDE.md "What
  changed" section + the 5 added unit tests in `tests/`).
- `frame-ancestors` already whitelists `*.rhpl.org`, `*.wixsite.com`,
  `*.wixstudio.com`, `*.wix.com`, `*.editorx.io` — that's set in
  app.py via response headers, not in the template. Don't add a
  conflicting `<meta http-equiv="Content-Security-Policy">`.
- 53 unit tests pass. Template changes are unlikely to break them,
  but run `.venv/bin/python -m pytest -q` before declaring done.
- This is iframed into Wix — the parent page provides the global
  nav/header/footer. Don't add chrome here. Keep
  `background: transparent` on body so the parent shows through.
- Don't ship to Cloud Run yet — Derek will repoint Wix only after
  Allison signs off (Tuesday 2026-05-26 email). Iterating on the
  template locally + deploying to the same Cloud Run service is fine;
  the iframe consumer is the rhpl-studio test site, not production
  rhpl.org.

## Related files

- `templates/embed.html` — the page being redesigned
- `wix/approach-a-iframe-embed.md` — iframe consumer setup +
  auto-resize listener snippet
- `wix/approach-b-velo-repeater.md` — alternative path (Velo +
  native Wix Repeater) we'd fall back to if iframe styling can't
  match the site
- `routes/public.py` — defines the `/embed` route + serves this template
- `routes/api.py` — defines `/api/databases.json`, the data source

## Accessibility audit (2026-05-24)

User asked for a full a11y audit with concern about alt text.
Comprehensive multi-tool audit run against the deployed `/embed`
endpoint (Cloud Run revision `esources-00017-76d`, bypassing the
5-min Firebase CDN to test fresh code).

### Tools used

- **axe-core 4.10.2** (Deque, the de-facto standard, WCAG 2.0/2.1
  A+AA + best-practice tags)
- **HTML_CodeSniffer 2.5.1** (Squiz, the engine behind pa11y —
  different rules than axe; pa11y CLI itself was broken on Node v26
  ESM, so HCS was loaded directly via Playwright)
- **Lighthouse 12.x** (Google, headless Chromium 1217)
- **Playwright manual probes**: keyboard tab order walk, accessible
  name inspection per card, computed color-contrast spot-check,
  heading hierarchy, prefers-reduced-motion respect
- Audit script lives at `/tmp/full_a11y.py` (session-local; copy
  into the repo as `scripts/a11y_audit.py` if you want it persisted)

### Final scores

| Tool              | Result                                              |
|-------------------|-----------------------------------------------------|
| axe-core          | **0 violations**, 1 incomplete (data issue, below), 28 passes |
| HTML_CodeSniffer  | **0 errors**, 75 warnings (HCS-limitation only), 117 notices |
| Lighthouse a11y   | **100 / 100**                                       |
| Manual contrast   | **9/9 elements pass WCAG 1.4.3 AA** (ratios 5.0–14.8) |
| Manual keyboard   | Logical tab order: filter buttons (1–18) → Visit buttons (19+ alphabetical) |
| WCAG 2.5.3        | Label-in-name ✓ on all sampled Visit buttons        |
| Heading hierarchy | H1 → H2 → H3, no skipped levels                     |
| Reduced motion    | ✓ `prefers-reduced-motion: reduce` honored          |

### Fixes shipped this session

All in `templates/embed.html`, deployed as revisions
`esources-00015-8kg`, `…-00016-5mr`, `…-00017-76d`:

1. **Badge moved out of `<h3>`** into a sibling `<span>` inside a
   new `.card-head` flex wrapper. Screen readers were previously
   reading "Geni ProIN-LIBRARY ONLY" as one mashed phrase; now the
   H3 reads "Geni Pro" and the badge reads separately. Affects ~25
   in-library-only cards.
2. **Dropped the redundant title link**. Cards had two links to the
   same URL (the H3 title and the "Visit" pill); keyboard/AT users
   had to Tab past both. H3 is now plain text; only the Visit
   button is focusable. Also fixed the `link-in-text-block`
   warning (no more color-only link distinction).
3. **Visit button gets a descriptive accessible name via sr-only
   span**: visible text "Visit" + sr-only " {database name},
   opens in new tab". Screen-reader users now hear "Visit Academic
   Search Complete, opens in new tab" instead of an ambiguous list
   of 74× "Visit". Also satisfies WCAG 3.2.5 (warn before
   opening new windows).
4. **`aria-label` removed** from Visit button — Lighthouse flagged
   `label-content-name-mismatch` (WCAG 2.5.3) on the first attempt
   because the aria-label diverged from the inner text. Now the
   accessible name comes purely from inner text (visible "Visit" +
   sr-only span), so the rule is mechanically satisfied.
5. **Article landmark labeled**: each `<article class="card">` has
   `aria-labelledby="dbh-{slug}"` pointing at its H3. Screen readers
   announce "Academic Search Complete, article" when entering a card.
6. **`.sr-only` utility class** added (`position: absolute; clip:
   rect(0,0,0,0); …`) — the standard screen-reader-only pattern.
7. **`prefers-reduced-motion: reduce` media query** added — disables
   the skeleton shimmer animation and the Visit button hover
   transition for users with vestibular-motion sensitivity.

### Alt text — short answer

The page has **zero `<img>` tags today**. The API
(`/api/databases.json`) exposes no image fields. Nothing to alt.

If we ever add database logos: emit `<img src="…" alt="">`
(decorative). The visible H3 already announces the database name; a
logo's alt text should be either the brand name (when it's the only
identifier) or empty when the name is already adjacent. **Do NOT
auto-populate alt from `description`** — descriptions describe what
the database *does*, alt text describes what the image *shows*.
Using descriptions as alt would trigger screen readers to read the
full marketing copy twice (once as image, once as visible paragraph)
and would technically misuse alt under WCAG H37.

### One pre-existing data issue (not blocking)

axe-core's 1 "incomplete" result is on the Rochester Hills Museum at
Van Hoosen Farm description, which has raw HTML embedded in the
Polaris source data:

> `Explore the Museum's <a href="...">collections</a> and <a href="...">newspapers</a>…`

We correctly HTML-escape on output (no XSS), so it renders as
literal angle-bracket gibberish on the page. Two options for a
follow-up task:

- **Strip on import**: have `migrate/import_extract.py` run
  `bleach.clean(text, tags=[], strip=True)` on the description
  field. Loses the intended links but cleans the display.
- **Render with allowlist**: switch the embed JS to use a
  carefully-scoped DOMParser approach, or have the API
  pre-render descriptions through `bleach.clean(text, tags=['a'],
  attributes={'a':['href','rel','target']})`. Keeps the links.

I'd recommend option 2 — the librarian's intent was clearly to link
to the museum's collections. Either way it's data hygiene, not
template work, so it should be its own ticket.

### HCS warnings explained (so the next reader doesn't worry)

The 75 HTML_CodeSniffer warnings are all variants of two codes:

- `WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Alpha` — "background
  contains transparency, can't verify contrast." Fires on every
  element whose computed background isn't a fully opaque color.
  Our manual contrast probe walked up the parent chain and verified
  the effective backgrounds; all 9 sampled element types pass AA
  with significant headroom.
- `WCAG2AA.…G18.Abs` — "element is absolutely positioned, can't
  determine background." Fires on `.sr-only` (which is positioned
  off-screen and never visually rendered, so contrast is moot).

Neither is a real defect. HCS is conservative by design.

## Open questions for Derek

- Are you OK with a sidebar filter, or do you want chips along the
  top to match the live page more literally?
- Should the "In-library only" badge use a different label? "In
  library" / "Library use only" / something else?
- Cards currently use the database `name` as the heading and link.
  The live site appears to also show vendor/publisher in some cases
  — do we want that here? It's not in `/api/databases.json` today.
