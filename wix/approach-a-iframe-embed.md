# Approach A — iframe-embed the catalog on rhpl-studio

Demo path for the new eSources catalog on the rhpl-studio test site, using a
plain `<iframe src="https://your-eresources-domain.org/embed">` widget. Zero Velo,
zero Custom Code required (Custom Code is optional polish for auto-resize).

## What this gives staff

A new page on rhpl-studio that renders the live catalog from Firestore.
Edit a record in https://your-eresources-domain.org/admin/ → reload the Wix page
→ change shows up (5-minute cache between admin save and Wix-side
visibility, controlled by the JSON endpoint's `Cache-Control: max-age=300`).

## Setup in Wix Studio editor (rhpl-studio site)

Recommended: create a NEW page (don't replace the existing `/databases`)
so staff can compare side-by-side.

1. **Open the editor for rhpl-studio** (Wix dashboard → rhpl-studio → Edit).
2. **Add a new page**:
   - Left rail → **Pages & Menu** → **+ Add Page** → **Blank**
   - Page Name: `Research Databases (new system)`
   - Page URL: `databases-iframe`
   - SEO description: leave default for now
3. **Optional: hide the page from the menu** during testing
   (Pages & Menu → click the page → SEO/Settings → toggle "Show in menu" off).
   Staff will reach it by direct URL during demo.
4. **Add an "Embed a Site" element**:
   - Left rail → **+ Add Elements** → **Embed Code** → **Embed a Site**
   - Drop on the canvas
   - Stretch to full width (drag the right handle out, or set width = 100%
     in Inspector → Layout)
   - **URL**: `https://your-eresources-domain.org/embed`
   - **Important — turn off the section's max-width cap.** Click the
     parent Section (e.g. `#section4`) and uncheck **"Apply max width"**
     in the Inspector. Wix Studio sections default to a ~1200px content
     cap; with it on, the iframe is squeezed to 1200px no matter what
     width you set on the iframe widget itself, which forces the catalog
     grid into 2 columns. Off → the section stretches edge-to-edge and
     the grid auto-fits 3+ columns on wide screens.
     - Alternative if full-bleed feels too sprawling on 4K: keep "Apply
       max width" on but raise the value to ~1800px (matches the embed
       page's internal `.wrap` cap, so you get up to 3 columns cleanly
       and the design stops stretching beyond that).
5. **Set initial iframe height** — the embed renders ~14,300px tall when
   showing all 134 category placements. Until you add the auto-resize
   snippet (step 6), set the Embed widget's height to **15500px** so the
   page scrolls naturally with no scrollbar inside the iframe.
   - In Inspector → Layout → Height: `15500`
6. **(Optional but recommended) Add the auto-resize snippet** so the
   iframe sizes itself dynamically — see "Auto-resize snippet" below.
7. **Publish** (top-right → Publish).

The page will be live at:
`https://vegapromoteweb.wixstudio.com/rhpl-studio/databases-iframe`

## Auto-resize snippet (optional)

The embed page already broadcasts its height to the parent via
`window.postMessage({ source: "rhpl-embed", height: <px> }, "*")`. Add
this snippet once in **Settings → Custom Code → Add Custom Code**:

- Name: `RHPL embed auto-resize`
- Place Code in: `<body>` (end)
- Apply to: `All pages` (it's a no-op on pages without the embed)

```html
<script>
(function () {
  function findEmbedIframe() {
    var frames = document.querySelectorAll('iframe');
    for (var i = 0; i < frames.length; i++) {
      var src = frames[i].src || '';
      if (src.indexOf('your-eresources-domain.org/embed') !== -1) return frames[i];
    }
    return null;
  }

  window.addEventListener('message', function (e) {
    if (!e.data || e.data.source !== 'rhpl-embed') return;
    var iframe = findEmbedIframe();
    if (!iframe) return;
    var h = Number(e.data.height) || 0;
    if (h > 200) {
      iframe.style.height = h + 'px';
      // Wix wraps the iframe in fixed-height containers. Walk up and
      // bump their height too, otherwise the iframe shows in a
      // scrollable inner box.
      var node = iframe.parentElement;
      for (var i = 0; i < 6 && node; i++, node = node.parentElement) {
        node.style.height = h + 'px';
        node.style.minHeight = h + 'px';
      }
    }
  });
})();
</script>
```

If the auto-resize works, you can drop the iframe's fixed height to
something small like 800px — the snippet will grow it to fit the content
as soon as the embed page loads.

## Verifying it works

After publishing:

1. Visit `https://vegapromoteweb.wixstudio.com/rhpl-studio/databases-iframe`
   in a private/incognito window (avoid cached Wix-editor state)
2. Wait for the iframe to render — should see 17 categories starting
   with "Alphabetical List" → "Academic Search Complete"
3. Click any database link — should open the gateway at
   `https://your-eresources-domain.org/go/<slug>` in a new tab
4. Confirm sync: edit a record in
   `https://your-eresources-domain.org/admin/` (e.g., disable one database),
   wait up to 5 minutes (or hard-reload to bypass cache), reload the
   Wix page — disabled record disappears

## Responsive column count

The embed's card grid uses CSS `grid-template-columns: repeat(auto-fit, minmax(380px, 1fr))`,
so the column count adapts to the **iframe's** rendered width (not the
visitor's browser width):

- iframe < ~1140px → 1 column
- ~1140–1520px → 2 columns
- ~1520–1900px → 3 columns
- wider → 4+ columns, capped by the embed's internal `.wrap` max-width
  of 1800px (cards stay readable, side margins grow)

Each column reserves the ~266px left sidebar (filter) plus a 380px-min
card width. If you're seeing fewer columns than expected, the iframe
itself is being squeezed — most commonly by the Wix Section's
"Apply max width" toggle (see step 4 above).

## Known limitations

- **Cold-load delay** — Wix bootstraps widgets ~3-5s after first paint on
  rhpl-studio (less than www.rhpl.org's 5-11s because no Vega Promote).
  The skeleton/loading state inside the iframe is visible during this
  window so the area is never blank.
- **5-minute cache** between admin save and Wix-visible change.
  Hard-reload (Cmd-Shift-R) bypasses it for testing.
- **Iframe scope** — the embedded page is on `your-eresources-domain.org`, so
  click counts/analytics on the Wix side won't capture launches. Add
  pageviews on the embed itself if needed.

## To roll back

Delete the page from Pages & Menu, optionally delete the Custom Code
entry. No other state to clean up.
