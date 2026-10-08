# Decision Viewer

A static website for searching and browsing sailing decisions.

**Website:** https://danilojoncic.github.io/rrs-decision-viewer/

## Add or update cases

Add one JSON file per case in [`data/decisions`](data/decisions/README.md), then
push or merge to `main`. GitHub Actions validates the files, rebuilds the complete
viewer, and publishes it to GitHub Pages. After deployment succeeds, refresh the
website to see the changes. Editing an existing file updates that case; removing
it removes that case from the next build. Hidden folders such as `.drafts` are
excluded. Invalid JSON prevents deployment and leaves the last successful site
available.

## Project structure

- `data/decisions/`: source case JSON files and their format instructions.
- `docs/`: the website HTML, CSS, JavaScript, flag, and generated case data.
- `scripts/`: case validation, normalization, and static build tools.
- `.github/workflows/pages.yml`: automatic validation and Pages publishing.
- `tests/offline_viewer.cjs`: browser checks.

Only `docs/` is deployed. The website runs entirely in the browser. Python is
used only during the build, using its standard library; no server or installed
Python dependencies are needed to use the site.

## Local build

```bash
python3 scripts/validate_cases.py
python3 scripts/build_github_pages.py
```

The build refreshes `docs/assets/decisions-data.js` and creates a standalone
`Decision Viewer.html` for offline use. Generated data excludes jury fields.
The header's update date comes from the build timestamp.

The editable website sources are `docs/index.html`, `docs/assets/styles.css`,
and `docs/assets/app.js`. Keep the assets directory alongside `docs/index.html`
when opening that version locally.

## GitHub Pages

In repository **Settings → Pages**, select **GitHub Actions** as the source.
Pushes to the default branch publish automatically. Pull requests and other
branches validate and build without deploying. The workflow can also be run
manually from the Actions tab. Generated files are published as an artifact;
the workflow does not commit them back to the repository.

## Browser checks

With Node, Playwright, and Chrome installed:

```bash
node tests/offline_viewer.cjs
```

Checks cover search, filters, navigation, dark mode, the Info dialog, the update
date, mobile layout, printing, and offline use.
