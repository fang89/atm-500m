# Methodology

This document explains, end to end, how the dashboard's numbers are produced —
enough detail to reproduce or audit every step. All code is in `scripts/`.

## 1. What is being measured, and why

On 25 June 2026 The Association of Banks in Singapore (ABS) published the
*Banking a Longevity Society* playbook. Its headline cash-access commitment
([media release, PDF](https://abs.org.sg/docs/library/singapore-banks-come-together-to-help-seniors-plan-well-age-well-and-ease-the-burden-on-their-loved-ones.pdf)):

> DBS, OCBC and UOB, together with NETS, have committed to providing an **ATM,
> branch or cashpoint within 500 metres of every HDB block by end-2027**.
> In the interim (end-2026): within 500 m of key public amenities — public
> transport hubs, NEA hawker centres, and major supermarkets (NTUC FairPrice,
> Sheng Siong, Cold Storage, Giant).

Three definitional points from the release that shape this analysis:

- **"500 metres" is straight-line distance** (release footnote 3), not walking
  distance. This analysis therefore also uses straight-line distance.
- A **"cashpoint"** is a NETS merchant offering cash-back during a purchase.
- The commitment is **industry-wide** (three banks + NETS pooled).

**Scope of this project:** the DBS/POSB network only. DBS/POSB runs Singapore's
largest ATM network and is historically the "people's bank" for seniors, so
"how far is the nearest DBS/POSB cash point" is a meaningful question in its
own right — but it is a **subset** of the commitment. Blocks flagged red here
may already be within 500 m of an OCBC/UOB ATM or a NETS cashpoint. In other
words, the dashboard shows a **lower bound on industry coverage** (equivalently,
an upper bound on the true number of gap blocks).

## 2. Data sources

| Data | Source | Vintage |
|---|---|---|
| HDB block locations | [HDB Existing Building](https://data.gov.sg/datasets/d_16b157c52ed637edd6ba1232e026258d/view) (GeoJSON, data.gov.sg) | dataset last updated Apr 2026 |
| Block attributes (street, town, dwelling units) | [HDB Property Information](https://data.gov.sg/datasets/d_17f5382f26140b1fdae0ba2ef6239d2f/view) (data.gov.sg) + [OneMap](https://www.onemap.gov.sg/) geocoding | fetched at generation date |
| DBS/POSB ATMs & branches | DBS branch-locator content API (the same data behind [dbs.com.sg's locator](https://www.dbs.com.sg/index/locator.page)) | fetched at generation date |

The generation date is shown in the dashboard footer and stored in
`docs/data/summary.json`.

### 2.1 HDB blocks (`data/hdb_existing_building.geojson`)

The *HDB Existing Building* dataset contains one polygon footprint per HDB
building — 13,436 features — each carrying `BLK_NO` and `POSTAL_COD` (the
6-digit postal code, which uniquely identifies a block). Coordinates are WGS84.

Processing (`scripts/analyze.py`):

1. For each feature, compute the **area-weighted centroid** of the largest
   polygon ring (standard shoelace centroid; planar approximation is exact to
   within centimetres at building scale). The centroid represents the block.
2. **Deduplicate by postal code** (a block drawn as several polygons — wings,
   annexes — keeps the largest-area feature).
3. Features with no postal code are kept, keyed by block number + rounded
   coordinates.

Note: the dataset is *all HDB buildings*, which includes multi-storey carparks
and commercial/institutional HDB buildings, not only residential blocks. This
matches the commitment's wording ("every HDB block") conservatively. Where the
optional OneMap enrichment (§2.3) has matched a block to the HDB Property
Information dataset, the dashboard shows street name and dwelling-unit count.

### 2.2 DBS/POSB cash points (`scripts/fetch_dbs_atms.py`)

The DBS locator web app loads its data from a public content API:

```
POST https://www.dbs.com.sg/sggenericcontent/v1/contentapi/
     flpstore_main_www_sg_mmcontent_dbsbranch/search        (Elasticsearch DSL)
```

The endpoint sits behind Akamai bot protection, so scripted HTTP requests are
rejected. The fetch script instead launches a headless Chromium via Playwright,
loads the locator page, and **records the API responses the page itself makes**
— i.e., exactly the data every visitor's browser receives. One request returns
all 2,315 DBS/POSB locations in Singapore with name, address, coordinates and a
service list.

Each location's services are classified (`scripts/analyze.py`):

| Category | Service codes | Counted as cash access? |
|---|---|---|
| **ATM** | `ATM` (Cash Withdrawal), `TKATM` (Talking ATM), `CRS` (Cash Recycling Service) | Yes — dispenses cash |
| **Branch** | `DBS`, `POSB`, `TR` (Treasures centre) | Yes — counter cash, per the commitment's "branch" |
| **Other** | `AXS` (bill kiosk), `CAM`/`CDM` (deposit only), `QCM`/`QCD` (cheques), `VTM` (video teller), SingPost counters, etc. | No — cannot withdraw cash |

Result: **765 ATM locations** and **73 retail branches** (a location offering
both counts once in each layer). Locations are deduplicated on rounded
coordinates + category. The dashboard's default "coverage" definition is
ATM-or-branch; a toggle restricts it to ATMs only.

### 2.3 Optional enrichment (`scripts/fetch_hdb_blocks.py`)

To display street names, towns and dwelling-unit counts, the HDB Property
Information dataset (12,000+ rows of `blk_no` + `street` + attributes, no
coordinates) is geocoded through OneMap's search API and joined to the
footprint centroids by postal code. OneMap throttles to roughly 1 request/s,
so this step takes ~3 h; it is resumable (cache in `data/hdb_geocode_cache.json`)
and purely cosmetic — no coverage number depends on it.

## 3. Distance computation

For every block centroid, the distance to the nearest ATM (and separately, the
nearest ATM-or-branch) is computed as **straight-line (great-circle) distance**,
using an equirectangular approximation calibrated at Singapore's latitude:

```
dx = Δlon × 111,320 m × cos(1.352°)
dy = Δlat × 110,574 m
d  = √(dx² + dy²)
```

At Singapore's scale (≤60 km extent, ≤1.5° from the equator) this differs from
exact geodesic distance by well under 0.1% — far below the noise introduced by
using building centroids.

Nearest-neighbour search uses a uniform grid hash (~700 m cells, expanding-ring
search), giving exact nearest distances in O(1) per block.

A block is a **gap** if its nearest cash point exceeds 500 m. The dashboard also
marks a 400–500 m "at the limit" band, since centroid-vs-door and
straight-line-vs-walk effects make blocks near the threshold ambiguous.

## 4. Known limitations

1. **DBS/POSB only.** No OCBC/UOB ATMs, no NETS cashpoints ⇒ coverage is
   understated; gap counts are an upper bound (see §1).
2. **Straight-line ≠ walking distance.** A block 480 m from an ATM across a
   canal or expressway is "covered" by the commitment's own definition but not
   in lived experience. (This cuts the other way from limitation 1.)
3. **Centroids, not doors.** Distances are centroid-to-point; for a large block
   the void deck entrance may differ by ±50 m.
4. **All HDB buildings included.** Some "blocks" are carparks or commercial
   HDB buildings. Filtering to residential-only (via the enrichment join)
   typically removes ~15–20% of buildings, concentrated inside estates —
   it changes gap counts only marginally.
5. **Point-in-time snapshot.** ATM networks change monthly; data.gov.sg
   footprints update quarterly. Re-run the pipeline to refresh (see README).
6. **Locator accuracy.** ATM coordinates are as published by DBS; a handful of
   entries carry mall-level rather than unit-level precision.

## 5. Reproducing

```bash
pip install playwright && playwright install chromium
python3 scripts/fetch_dbs_atms.py         # ~1 min: captures locator API via browser
# download the HDB Existing Building GeoJSON from data.gov.sg into data/
python3 scripts/fetch_hdb_blocks.py       # optional, ~3 h: street/town enrichment
python3 scripts/analyze.py                # seconds: writes docs/data/*.json
cd docs && python3 -m http.server 8000    # view at http://localhost:8000
```

`docs/` is fully static (Leaflet from CDN, no build step); publish it on any
static host.

## 6. Licences & attribution

- HDB datasets: © Housing & Development Board / data.gov.sg,
  [Singapore Open Data Licence](https://data.gov.sg/open-data-licence).
- Geocoding: © Singapore Land Authority (OneMap), Singapore Open Data Licence.
- ATM/branch data: © DBS Bank Ltd, retrieved from DBS's public locator API for
  research and commentary, with attribution. This project is not affiliated
  with or endorsed by DBS, ABS, or any government agency.
- Basemap tiles: © OpenStreetMap contributors, © CARTO.
