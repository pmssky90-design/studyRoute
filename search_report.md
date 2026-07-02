# Search Implementation Report

## Summary

- Implemented the main header search interaction for the existing magnifier button.
- Added automatic `search-index.json` generation from generated `Page` metadata.
- Added client-only search with lightweight JavaScript. No server search is used.
- Preserved generator page structure, SEO fields, URLs, slugs, titles, breadcrumbs, JSON-LD, robots, and sitemap logic.

## Files Changed

- `generator.py`
  - Added `write_search_index(pages)`.
  - Writes `output/search-index.json` after assets are copied.
  - Index fields: `url`, `title`, `slug`.
- `templates/partials/header.html`
  - Added the expandable search panel and result container next to the existing search icon.
- `templates/base.html`
  - Loads `assets/js/search.js` with `defer`.
- `assets/js/search.js`
  - Opens/closes search on icon click.
  - Closes on repeated click, `ESC`, and outside click.
  - Fetches only `search-index.json`.
  - Scores slug/title/url matches with prefix, contains, and lightweight fuzzy matching.
  - Navigates to the selected result URL.
- `assets/css/main.css`
  - Added desktop dropdown search UI.
  - Added mobile full-screen search UI.
  - Added transition and result list styling.
- `scripts/verify_search.py`
  - Added Edge headless verification for Desktop, Tablet, and Mobile.

## Generated Output

- `output/search-index.json`
  - Page count: `1976`
  - Size: about `395 KB`
- `output/assets/js/search.js`
- Updated generated HTML pages include the search script and panel.

## Verification

Command run:

```powershell
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' scripts\verify_search.py
```

Result: passed.

Verified viewports:

- Desktop `1440x1000`
  - Query: `대전`
  - Search opened, 8 autocomplete results shown.
  - First result click navigated to `/대전과외/`.
  - `ESC` close: passed.
  - Outside click close: passed.
- Tablet `820x1100`
  - Query: `관평`
  - Search opened, 8 autocomplete results shown.
  - First result click navigated to `/관평동과외/`.
  - `ESC` close: passed.
  - Outside click close: passed.
- Mobile `390x844`
  - Query: `수학`
  - Search opened as a full-screen panel.
  - 8 autocomplete results shown.
  - First result click navigated to `/수학과외/`.
  - `ESC` close: passed.
  - Outside click close: passed.

Verification artifacts:

- `reports/search_verify_results.json`
- `reports/search-desktop.png`
- `reports/search-tablet.png`
- `reports/search-mobile.png`
