#!/usr/bin/env python3
"""Compute 500m cash-access coverage for every HDB block.

Inputs:
  data/hdb_existing_building.geojson  (HDB block footprints, data.gov.sg)
  data/dbs_raw.json                   (DBS locator content-API capture)
  data/hdb_blocks.json                (optional OneMap enrichment: street/town/units)

Outputs (dashboard-ready, in docs/data/):
  atms.json     [{name, addr, lat, lon, cat}]  cat: atm | branch | other
  blocks.json   [[postal, blk, lat, lon, dist_atm_m, dist_any_m, street, town, units], ...]
  summary.json  headline stats
"""
import json
import math
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "docs", "data")
os.makedirs(OUT, exist_ok=True)

# Cash-withdrawal machine services (per ABS announcement: ATM counts; talking
# ATMs and cash recyclers dispense cash too). Deposit-only machines (CAM, CDM,
# QCM), AXS kiosks etc. do NOT count.
CASH_MACHINE = {"ATM", "TKATM", "CRS"}
RETAIL_BRANCH = {"DBS", "POSB", "TR"}  # TR = Treasures centres (staffed)

# Postal sector (first 2 digits) -> broad area, URA postal district scheme
SECTOR_AREA = {
    "01": "Raffles Place/Marina", "02": "Raffles Place/Marina", "03": "Raffles Place/Marina",
    "04": "Harbourfront", "05": "Harbourfront", "06": "Raffles Place/Marina",
    "07": "Bugis/Rochor", "08": "Little India", "09": "Orchard/River Valley",
    "10": "Orchard/River Valley", "14": "Queenstown/Tiong Bahru", "15": "Queenstown/Tiong Bahru",
    "16": "Queenstown/Tiong Bahru", "11": "Chinatown/Outram", "12": "Balestier/Toa Payoh",
    "13": "Balestier/Toa Payoh", "17": "Bukit Merah", "18": "Bukit Merah",
    "19": "Tanglin/Holland", "20": "Ang Mo Kio/Bishan", "21": "Clementi/West Coast",
    "22": "Jurong", "23": "Jurong", "24": "Lim Chu Kang", "25": "Kranji/Woodgrove",
    "26": "Upper Thomson", "27": "Yishun/Sembawang", "28": "Seletar",
    "29": "Novena/Thomson", "30": "Novena/Thomson", "31": "Toa Payoh/Serangoon",
    "32": "Toa Payoh/Serangoon", "33": "Toa Payoh/Serangoon",
    "34": "Macpherson/Potong Pasir", "35": "Macpherson/Potong Pasir",
    "36": "Macpherson/Potong Pasir", "37": "Macpherson/Potong Pasir",
    "38": "Geylang/Eunos", "39": "Geylang/Eunos", "40": "Geylang/Eunos",
    "41": "Geylang/Eunos", "42": "Katong/Joo Chiat", "43": "Katong/Joo Chiat",
    "44": "Katong/Joo Chiat", "45": "Katong/Joo Chiat", "46": "Bedok/Upper East Coast",
    "47": "Bedok/Upper East Coast", "48": "Bedok/Upper East Coast",
    "49": "Loyang/Changi", "50": "Loyang/Changi", "51": "Tampines/Pasir Ris",
    "52": "Tampines/Pasir Ris", "53": "Serangoon Gdn/Hougang", "54": "Serangoon Gdn/Hougang",
    "55": "Serangoon Gdn/Hougang", "56": "Ang Mo Kio/Bishan", "57": "Ang Mo Kio/Bishan",
    "58": "Bukit Timah/Ulu Pandan", "59": "Bukit Timah/Ulu Pandan",
    "60": "Jurong", "61": "Jurong", "62": "Jurong", "63": "Jurong", "64": "Jurong",
    "65": "Bukit Panjang/CCK", "66": "Bukit Panjang/CCK", "67": "Bukit Panjang/CCK",
    "68": "Bukit Panjang/CCK", "69": "Lim Chu Kang/Tengah", "70": "Lim Chu Kang/Tengah",
    "71": "Lim Chu Kang/Tengah", "72": "Kranji/Woodgrove", "73": "Kranji/Woodgrove",
    "75": "Yishun/Sembawang", "76": "Yishun/Sembawang", "77": "Seletar", "78": "Seletar",
    "79": "Serangoon Gdn/Hougang", "80": "Serangoon Gdn/Hougang",
    "81": "Loyang/Changi", "82": "Punggol/Sengkang",
}

M_PER_DEG_LAT = 110574.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(1.352))


def dist_m(lat1, lon1, lat2, lon2):
    dy = (lat1 - lat2) * M_PER_DEG_LAT
    dx = (lon1 - lon2) * M_PER_DEG_LON
    return math.hypot(dx, dy)


def polygon_centroid(ring):
    """Area-weighted centroid of a lon/lat ring (planar approx, fine at block scale)."""
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(ys) / len(ys), sum(xs) / len(xs)
    return cy / (3 * a), cx / (3 * a)  # lat, lon


def load_atms():
    raw = json.load(open(os.path.join(DATA, "dbs_raw.json")))
    hits = next(x for x in raw if x["url"].endswith("dbsbranch/search"))["body"]["hits"]["hits"]
    atms, seen = [], set()
    for h in hits:
        rd = h["_source"]["results_data"]
        try:
            lat, lon = float(rd["latitude"]), float(rd["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (1.1 < lat < 1.5 and 103.5 < lon < 104.2):
            continue
        li = rd.get("localeItem") or {}
        if isinstance(li, list):
            li = li[0] if li else {}
        bl = rd.get("branchServicesList") or []
        if isinstance(bl, dict):
            bl = [bl]
        codes = {s.get("serviceCode", "") for s in bl}
        if codes & CASH_MACHINE:
            cat = "atm"
        elif codes & RETAIL_BRANCH:
            cat = "branch"
        else:
            cat = "other"
        key = (round(lat, 5), round(lon, 5), cat)
        if key in seen:
            continue
        seen.add(key)
        atms.append({
            "name": li.get("name", "").strip(),
            "addr": li.get("address", "").strip(),
            "postal": (rd.get("postal_code") or "").replace("Singapore", "").strip(),
            "lat": round(lat, 6), "lon": round(lon, 6),
            "cat": cat,
            "svc": sorted(codes - {""}),
        })
    return atms


class Grid:
    """Bucket points into ~700m cells for fast nearest-neighbour lookup."""
    CELL = 0.0063  # degrees, ~700m

    def __init__(self, pts):
        self.pts = pts
        self.cells = defaultdict(list)
        for i, (lat, lon) in enumerate(pts):
            self.cells[(int(lat / self.CELL), int(lon / self.CELL))].append(i)

    def nearest(self, lat, lon):
        ci, cj = int(lat / self.CELL), int(lon / self.CELL)
        best, best_i = float("inf"), -1
        ring = 0
        while True:
            found_any = False
            for i in range(ci - ring, ci + ring + 1):
                for j in range(cj - ring, cj + ring + 1):
                    if ring and max(abs(i - ci), abs(j - cj)) < ring:
                        continue
                    for k in self.cells.get((i, j), ()):
                        found_any = True
                        d = dist_m(lat, lon, *self.pts[k])
                        if d < best:
                            best, best_i = d, k
            # done once we've searched one ring beyond the best hit
            if best_i >= 0 and ring * self.CELL * M_PER_DEG_LAT > best + 700:
                return best, best_i
            ring += 1
            if ring > 60:
                return best, best_i


def load_blocks():
    g = json.load(open(os.path.join(DATA, "hdb_existing_building.geojson")))
    merged = {}
    for f in g["features"]:
        p = f["properties"]
        blk = (p.get("BLK_NO") or "").strip()
        postal = (p.get("POSTAL_COD") or "").strip()
        geom = f["geometry"]
        rings = []
        if geom["type"] == "Polygon":
            rings = [geom["coordinates"][0]]
        elif geom["type"] == "MultiPolygon":
            rings = [poly[0] for poly in geom["coordinates"]]
        if not rings:
            continue
        lat, lon = polygon_centroid(max(rings, key=len))
        key = postal or f"{blk}@{round(lat,4)},{round(lon,4)}"
        area = p.get("SHAPE.AREA") or 0
        if key not in merged or area > merged[key][3]:
            merged[key] = (blk, lat, lon, area, postal)
    return [(blk, lat, lon, postal) for blk, lat, lon, _, postal in merged.values()]


def load_enrichment():
    """OneMap-geocoded property info: postal -> (street, town, units)."""
    path = os.path.join(DATA, "hdb_blocks.json")
    if not os.path.exists(path):
        return {}
    enr = {}
    for b in json.load(open(path)):
        if b.get("postal"):
            enr[b["postal"]] = (b["street"], b["town"], b["units"])
    return enr


def load_cashpoints():
    path = os.path.join(DATA, "cashpoints.json")
    return json.load(open(path)) if os.path.exists(path) else []


def main():
    atms = load_atms()
    cashpoints = load_cashpoints()
    pts_a = [(a["lat"], a["lon"]) for a in atms if a["cat"] == "atm"]
    pts_ab = [(a["lat"], a["lon"]) for a in atms if a["cat"] in ("atm", "branch")]
    pts_c = [(c["lat"], c["lon"]) for c in cashpoints]
    names_atm = [a for a in atms if a["cat"] == "atm"]
    print(f"{len(atms)} DBS locations: {len(pts_a)} ATM sites, "
          f"{len(pts_ab)-len(pts_a)} branches; {len(pts_c)} cashpoints", flush=True)

    grid_a, grid_ab = Grid(pts_a), Grid(pts_ab)
    grid_ac, grid_abc = Grid(pts_a + pts_c), Grid(pts_ab + pts_c)
    blocks = load_blocks()
    enr = load_enrichment()
    print(f"{len(blocks)} HDB blocks, enrichment for {len(enr)}", flush=True)

    out_blocks = []
    for blk, lat, lon, postal in blocks:
        d_a, i_atm = grid_a.nearest(lat, lon)
        d_ab, _ = grid_ab.nearest(lat, lon)
        d_ac, _ = grid_ac.nearest(lat, lon)
        d_abc, _ = grid_abc.nearest(lat, lon)
        street, town, units = enr.get(postal, ("", "", 0))
        out_blocks.append([
            postal, blk, round(lat, 6), round(lon, 6),
            round(d_a), round(d_ab),
            street, town, units,
            names_atm[i_atm]["name"] if i_atm >= 0 else "",
            round(d_ac), round(d_abc),
        ])

    n = len(out_blocks)
    over = {k: sum(1 for b in out_blocks if b[i] > 500)
            for k, i in [("atm", 4), ("atm_or_branch", 5),
                         ("atm_or_cashpoint", 10), ("all", 11)]}
    summary = {
        "generated": __import__("datetime").date.today().isoformat(),
        "blocks": n,
        "atm_sites": len(pts_a),
        "branches": len(pts_ab) - len(pts_a),
        "cashpoints": len(pts_c),
        "blocks_over_500m_atm": over["atm"],
        "blocks_over_500m_atm_or_branch": over["atm_or_branch"],
        "blocks_over_500m_atm_or_cashpoint": over["atm_or_cashpoint"],
        "blocks_over_500m_all": over["all"],
        "pct_covered_atm": round(100 * (n - over["atm"]) / n, 1),
        "pct_covered_any": round(100 * (n - over["atm_or_branch"]) / n, 1),
        "pct_covered_all": round(100 * (n - over["all"]) / n, 1),
        "median_dist_atm": sorted(b[4] for b in out_blocks)[n // 2],
        "p90_dist_atm": sorted(b[4] for b in out_blocks)[int(n * 0.9)],
        "max_dist_atm": max(b[4] for b in out_blocks),
    }
    json.dump(atms, open(os.path.join(OUT, "atms.json"), "w"))
    json.dump(cashpoints, open(os.path.join(OUT, "cashpoints.json"), "w"))
    json.dump(out_blocks, open(os.path.join(OUT, "blocks.json"), "w"))
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
