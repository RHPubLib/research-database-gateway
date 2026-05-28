# Approach B — Velo + Wix Repeater (native Wix UI)

The Wix-native variant: a real Wix Studio Repeater element bound to the
`/api/databases.json` feed via Velo page code. Renders with full Wix
styling (matches the rest of the site's design system, accessible by
default, picks up any global theme changes automatically).

Requires more editor setup than Approach A. Recommended only after staff
confirms they want the Wix-native look — otherwise Approach A is a
faster demo with the same data underneath.

## Setup in Wix Studio editor (rhpl-studio site)

### 1. Create the page

- Wix dashboard → rhpl-studio → Edit
- Pages & Menu → **+ Add Page** → **Blank**
- Page Name: `Research Databases (Velo)`
- Page URL: `databases-velo`
- Hide from menu during testing (Settings → toggle "Show in menu" off)

### 2. Add the page elements

On the new blank page, drop these elements from **+ Add Elements**. The
**Element IDs in the Inspector panel MUST match exactly** — Velo code
references them by ID and silently does nothing if they're missing.

| # | Element type | Where to find it | Element ID | Default state |
|---|---|---|---|---|
| 1 | **Text** ("Heading 1") | + Add → Text → Heading 1 | `dbPageTitle` | "Research Databases" |
| 2 | **Text** ("Paragraph") | + Add → Text → Paragraph | `dbLoadingText` | Visible. Text: "Loading databases…" |
| 3 | **Text** ("Paragraph") | + Add → Text → Paragraph | `dbErrorText` | **Hidden** (toggle in Inspector → "Show on load" off) |
| 4 | **Repeater** | + Add → List → Classic Repeater | `dbRepeater` | Hidden on load |

### 3. Design the repeater item template

Click into one repeater item (Wix calls this "editing the connected item"
— double-click an item to enter design mode). Inside ONE item, add:

| Sub-element | Type | Element ID | Notes |
|---|---|---|---|
| Database name | **Text** (Heading 3) | `dbName` | Will be set per-item |
| Description | **Text** (Paragraph) | `dbDescription` | Will be set per-item |
| Launch button | **Button** | `dbLink` | Label: "Open Database →" |

Wix automatically clones the item template for every record in the
bound data. **Only design ONE item.**

### 4. Add the Velo page code

Top toolbar → **`</> Code`** (turn on Velo if not already enabled).
Click into the page's code panel (a tab named after the page slug, e.g.
`databases-velo.js`). Paste the code from
[`velo_page_code.js`](./velo_page_code.js) in this folder.

### 5. Publish

Top right → **Publish**.

The page goes live at:
`https://vegapromoteweb.wixstudio.com/rhpl-studio/databases-velo`

## Verifying it works

1. Visit the published URL in incognito (avoid editor-state caching)
2. You should briefly see "Loading databases…", then the repeater
   appears with 74 unique databases (Approach B deduplicates
   cross-listings; Approach A renders cross-listings as separate rows)
3. Click any "Open Database →" button → opens the gateway in a new tab
4. If you see "Loading databases…" forever: open browser DevTools
   console, look for `Failed to load databases` — usually a CORS issue
   (we set `Access-Control-Allow-Origin: *` on the JSON endpoint, so
   this should not happen) or an element-ID typo

## Optional: add category filter

Once the minimal version works, you can add a category Dropdown filter:

1. Drop a **Dropdown** element above the repeater, ID = `dbCategoryDropdown`
2. Drop a **Text** element (Paragraph) for the count, ID = `dbCount`
3. Replace the Velo code with the "full version" — code TBD; ask Claude
   to extend `velo_page_code.js` with the dropdown logic once the
   minimal version is verified working

## Comparing A and B for staff

| Aspect | Approach A (iframe) | Approach B (Velo + Repeater) |
|---|---|---|
| Wix-native look | No (our own CSS) | Yes (inherits site theme) |
| Editor setup time | ~5 minutes | ~30 minutes |
| Iteration time after first setup | Instant (redeploy our embed) | ~5 minutes (Velo code edit + publish) |
| Cross-listings | Shows each placement | Deduplicated to unique databases |
| Cold-load timing | ~3-5s on rhpl-studio | ~3-5s + Velo init (similar) |
| Accessibility | Our hand-rolled HTML | Wix's built-in semantics |
| Reverts | Delete page | Delete page + Velo code |

## To roll back

Delete the page (and the Velo code on it) from Pages & Menu. No other
state to clean up.
