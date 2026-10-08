# Decision Viewer

An offline sailing protest and redress decision library, with an optional FastAPI application.

## Automatic GitHub Pages publishing

Case files live in [`data/decisions`](data/decisions/README.md), one JSON per case.
The repository includes `.github/workflows/pages.yml` to validate and rebuild on
every push and pull request. Successful pushes to the default branch publish the
complete updated viewer; other branches and pull requests only validate/build.

One-time setup:

1. Push this project to your GitHub repository, including `.github/workflows`,
   `app`, `scripts`, `docs`, and `data/decisions`.
2. In **Settings → Pages → Build and deployment**, set **Source** to
   **GitHub Actions**.
3. In **Actions → Build and publish decisions**, choose **Run workflow** on the
   default branch for the first deployment (or push another commit).
4. Open the website URL shown by the successful deployment.

After setup, add or update case JSON files in `data/decisions` and push/merge to
the default branch. All cases are rebuilt together, including search and filter
options. Refresh the website after deployment completes. The workflow publishes
`docs` as an artifact and does not commit generated files back to the repository.
No Python dependencies, personal access token, or backend server are required.

Invalid JSON stops publication and reports the file in Actions; the previous
successful deployment stays available. Existing `data/imports` files are also
included for compatibility. Files in hidden directories are excluded.

## Open the offline viewer

Double-click **`Decision Viewer.html`** in this folder. It includes all **582 decisions
from 60 events** and works directly in a normal browser with no internet connection,
server, or installation. You can copy this single file to another computer.

- Search as you type across the full record. Use quotation marks for a phrase,
  `-word` to exclude a term, or field searches such as `rule:11`, `event:"Kieler
  Woche"`, `party:USA`. Press `/` to focus search.
- Combine event, hearing type, year, and rule filters.
  Rule filters can require **any** or **all** selections.
  Counts update against the rest of the active search and filters.
- Sort by relevance, event, newest first, or most rules. Result previews show the
  fact, conclusion, or decision text that matched the query.
- Open a result to read the complete case immediately: procedures, facts, rules,
  conclusions, and the decision. Click a rule to find other cases using it.
- Use Previous / Next to move through your filtered results, **Expand** for a larger
  reader, or **Print** to print the case. Press `Escape` outside a text field to
  leave the expanded view.
The viewer is read-only. It has no editing, importing, creation, or deletion controls.
Previously saved browser edits are ignored and left untouched. Search and selected
filters remain in the URL, so they survive reloads and can be bookmarked.

Search also accepts `rules:`, `facts:`, `year:`, and `case:` (source filename).
Quoted phrases match whole words; names can be searched without accents. All-mode
facet counts show the intersection with the currently selected rules.

Six source records were corrected during the read-only refresh: misplaced
conclusions, a publication timestamp in the jury list, and hearing-type spelling.
`data/cleanup-log.json` records every change with its original and corrected data.
Ambiguous source text is retained, with source warnings where available.

## Optional server application

The original FastAPI application remains available for the broader Casebook,
Appendix N, and Wording tools. Those server tools are separate from the standalone
decision viewer.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

The platform has four tabs:

- Decisions: imported hearing decision JSON files.
- Casebook: active World Sailing casebook cases from `/Users/danilo/Desktop/cases.pdf`.
- Appendix N: an international-jury hearing simulator backed by `/Users/danilo/Desktop/rrs json/rules.json`.
- Wording: searchable preferred standard wording backed by `/Users/danilo/Desktop/wording.xlsx`.

## Docker

The Docker image is self-contained. It includes:

- app templates and static assets
- decision JSON files in `data/decisions`
- active casebook data in `data/casebook`
- Appendix N rules in `data/rules/rules.json`
- preferred wording workbook in `data/wording/wording.xlsx`

Build and run:

```bash
docker build -t judging-platform:latest .
docker run --rm -p 8000:8000 judging-platform:latest
```

For more CPU parallelism, set the Uvicorn worker count:

```bash
docker run --rm -p 8000:8000 -e WEB_CONCURRENCY=2 judging-platform:latest
```

To mount an existing additional decision library:

```bash
docker volume create judging-imports
docker run --rm -p 8000:8000 -v judging-imports:/app/data/imports judging-platform:latest
```

## Static viewer maintenance

The viewer sources are `docs/index.html`, `docs/assets/styles.css`, and
`docs/assets/app.js`. `docs/index.html` also works offline if its `assets` folder
is kept beside it.

To include new decision JSON files, place them in `data/decisions` and rebuild:

```bash
python3 scripts/build_github_pages.py
```

This regenerates the search data and the standalone `Decision Viewer.html`.
The build uses the existing repository normalization and requires only Python's
standard library. Source corrections are recorded in `data/cleanup-log.json`. The standalone file has
no external scripts, fonts, images, fetch requests, or runtime dependencies.
Imported text is escaped before embedding it into HTML.

The `docs` directory can also be served by any static host. Hosting is optional.

### Browser verification

`tests/offline_viewer.cjs` checks the standalone file in headless Chrome with
networking disabled. With Node, Playwright, and Chrome installed, run:

```bash
node tests/offline_viewer.cjs
```

It covers full-text and field-aware search, exact rule matching, exclusions,
combined any/all filters, pagination, read-only behavior and legacy-edit isolation,
history navigation, printing, mobile overflow, unavailable browser storage, and
zero network requests.

## Server configuration

By default the app reads JSON files from:

```text
data/decisions
```

The server also reads existing records in `data/imports`. Import and update API endpoints have been removed.

To point it at another folder:

```bash
DECISIONS_JSON_DIR="/path/to/decisions" .venv/bin/uvicorn app.main:app --reload
```

To point imports at another folder:

```bash
DECISIONS_IMPORT_DIR="/path/to/imports" .venv/bin/uvicorn app.main:app --reload
```

The app skips hidden folders such as `.drafts`, indexes every visible `.json` file recursively, and refreshes the in-memory index when files change.

## World Sailing Casebook

The active-only extracted casebook data is stored at:

```text
data/casebook/world_sailing_cases.json
```

Regenerate it from the PDF with:

```bash
python3 scripts/import_casebook_pdf.py
```

By default this excludes deleted and withdrawn case stubs. The importer has an `--include-inactive` flag for audits, but the app viewer still filters to active cases.

To point the importer or app at another casebook PDF/data file:

```bash
CASEBOOK_PDF_PATH="/path/to/cases.pdf" python3 scripts/import_casebook_pdf.py
CASEBOOK_DATA_PATH="/path/to/world_sailing_cases.json" .venv/bin/uvicorn app.main:app --reload
```

To point the Appendix N simulator at another rules JSON file:

```bash
RRS_RULES_JSON_PATH="/path/to/rules.json" .venv/bin/uvicorn app.main:app --reload
```

To point the preferred wording tab at another workbook:

```bash
WORDING_XLSX_PATH="/path/to/wording.xlsx" .venv/bin/uvicorn app.main:app --reload
```

Jury names are not displayed, indexed for search, or included in the generated viewer data or decision API responses. Original source JSON files are retained for archival use.
