/* Velo page code for `databases-velo` on rhpl-studio.
 *
 * Fetches https://your-eresources-domain.org/api/databases.json and binds the
 * results to the Repeater whose Wix Element ID is `#dbRepeater`. The
 * Wix editor must have these elements present (see approach-b-velo-repeater.md):
 *
 *   #dbLoadingText  — Text, visible on load     ("Loading databases…")
 *   #dbErrorText    — Text, hidden on load      (error message goes here)
 *   #dbRepeater     — Classic Repeater, hidden on load
 *   inside the repeater item template:
 *     #dbName        — Text
 *     #dbDescription — Text
 *     #dbLink        — Button (rendered as the launch link)
 *
 * After editing, click "Save" then "Publish" in the Wix editor.
 */
import { fetch } from 'wix-fetch';

const JSON_URL = 'https://your-eresources-domain.org/api/databases.json';

$w.onReady(async function () {
  $w('#dbLoadingText').show();
  $w('#dbErrorText').hide();
  $w('#dbRepeater').hide();

  try {
    const response = await fetch(JSON_URL);
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    const data = await response.json();

    // The JSON feed renders cross-listed databases once per category
    // placement. For the Velo demo, deduplicate to unique databases
    // (74 unique vs 134 placements) so the Repeater isn't cluttered.
    const dbsBySlug = {};
    (data.databases || []).forEach(db => {
      if (!dbsBySlug[db.slug]) dbsBySlug[db.slug] = db;
    });

    const items = Object.values(dbsBySlug)
      .sort((a, b) => String(a.name).localeCompare(String(b.name)))
      .map(db => ({
        // Wix Repeater requires a string `_id` on every item.
        _id: 'db-' + db.slug,
        name: db.name,
        description: db.description || '',
        launchUrl: db.launch_url,
      }));

    // Bind the per-item rendering before assigning data so the first
    // pass populates correctly.
    $w('#dbRepeater').onItemReady(($item, item) => {
      $item('#dbName').text = item.name;
      $item('#dbDescription').text = item.description;
      $item('#dbLink').link = item.launchUrl;
      $item('#dbLink').target = '_blank';
    });

    $w('#dbRepeater').data = items;

    $w('#dbLoadingText').hide();
    $w('#dbRepeater').show();
  } catch (err) {
    console.error('Failed to load databases:', err);
    $w('#dbLoadingText').hide();
    $w('#dbErrorText').text =
      'Could not load databases. ' + (err && err.message ? err.message : err);
    $w('#dbErrorText').show();
  }
});
