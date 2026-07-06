# Every HDB block vs the nearest DBS/POSB ATM

Interactive map of how far every HDB block in Singapore is from the nearest
DBS/POSB cash point, against the banking industry's commitment (ABS, 25 Jun 2026)
to put an ATM, bank branch or NETS cashpoint within 500 m of every HDB block by
end-2027.

**Live dashboard:** `docs/index.html` (serve statically; see Deploy below)

## Headline findings (as of the generated date in the dashboard)

- 13,436 HDB buildings; 765 DBS/POSB ATM locations + 73 branches
- ~5% of blocks (≈700) are more than 500 m straight-line from the nearest
  DBS/POSB cash point; the worst block is ~940 m away
- Median distance is ~240 m; biggest gap clusters: Tampines/Pasir Ris,
  Woodlands, Jurong, Bukit Panjang/CCK, Punggol/Sengkang

**Important caveat:** the ABS commitment is industry-wide (DBS + OCBC + UOB +
NETS cashpoints). This project maps only the DBS/POSB network, so it
*underestimates* actual coverage — a "gap" block here may already be served by
another bank or a NETS cashpoint. Distances are straight-line, per the ABS
release's own definition.

## Repo layout

```
scripts/fetch_dbs_atms.py     # DBS locator content-API capture (needs Playwright)
scripts/fetch_hdb_blocks.py   # HDB property info + OneMap geocoding (optional enrichment)
scripts/analyze.py            # nearest-ATM distance per block -> docs/data/*.json
data/                         # raw inputs (HDB Existing Building geojson, DBS capture)
docs/                         # the static dashboard (publish this folder)
```

## Refresh the data

```bash
python3 scripts/fetch_dbs_atms.py     # ~1 min, real browser via Playwright
# HDB Existing Building geojson: download from data.gov.sg into data/ (see link below)
python3 scripts/fetch_hdb_blocks.py   # optional, slow (OneMap rate limits): street/town enrichment
python3 scripts/analyze.py            # rebuilds docs/data/{blocks,atms,summary}.json
```

## Run locally

```bash
cd docs && python3 -m http.server 8000   # then open http://localhost:8000
```

## Deploy (free)

**GitHub Pages** (simplest): push this repo to GitHub → repo Settings → Pages →
"Deploy from a branch" → branch `main`, folder `/docs`. The dashboard is plain
static HTML + JSON, no build step.

Alternatives: Cloudflare Pages, Netlify, Vercel (all free for static sites) —
point them at the repo, set the output directory to `docs/`.

## Sources & licences

- [ABS media release, 25 Jun 2026](https://abs.org.sg/docs/library/singapore-banks-come-together-to-help-seniors-plan-well-age-well-and-ease-the-burden-on-their-loved-ones.pdf)
- [HDB Existing Building](https://data.gov.sg/datasets/d_16b157c52ed637edd6ba1232e026258d/view) and
  [HDB Property Information](https://data.gov.sg/datasets/d_17f5382f26140b1fdae0ba2ef6239d2f/view)
  — data.gov.sg, [Singapore Open Data Licence](https://data.gov.sg/open-data-licence)
- ATM/branch locations: DBS public branch-locator API (© DBS Bank; used here for
  research/commentary with attribution — not affiliated with or endorsed by DBS)
- Geocoding: [OneMap](https://www.onemap.gov.sg/), Singapore Land Authority
- Basemap: © OpenStreetMap contributors, © CARTO
