#!/usr/bin/env python3
"""Download every HDB block from data.gov.sg and geocode it via OneMap.

Source: HDB Property Information dataset (d_17f5382f26140b1fdae0ba2ef6239d2f).
Geocoding: OneMap search API (free, ~250 calls/min). Resumable: results are
cached in data/hdb_geocode_cache.json so re-runs only fetch what's missing.

Output: data/hdb_blocks.json  [{blk, street, lat, lon, town, units, residential}]
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

DATASET = "d_17f5382f26140b1fdae0ba2ef6239d2f"
DGS_URL = "https://data.gov.sg/api/action/datastore_search"
ONEMAP_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

RAW_PATH = os.path.join(DATA, "hdb_property_info.json")
CACHE_PATH = os.path.join(DATA, "hdb_geocode_cache.json")
OUT_PATH = os.path.join(DATA, "hdb_blocks.json")


def http_json(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            wait = 2 ** i
            print(f"  retry {i+1} in {wait}s: {e}", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"gave up on {url}")


def download_property_info():
    if os.path.exists(RAW_PATH):
        with open(RAW_PATH) as f:
            return json.load(f)
    rows, offset = [], 0
    while True:
        url = f"{DGS_URL}?resource_id={DATASET}&limit=5000&offset={offset}"
        res = http_json(url)["result"]
        batch = res["records"]
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        print(f"downloaded {offset} rows", flush=True)
        if offset >= res.get("total", 0):
            break
    with open(RAW_PATH, "w") as f:
        json.dump(rows, f)
    return rows


def geocode(query):
    q = urllib.parse.quote(query)
    url = f"{ONEMAP_URL}?searchVal={q}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
    res = http_json(url)
    for r in res.get("results", []):
        # Prefer exact block number match
        if r.get("BLK_NO", "").strip().upper() == query.split()[0].upper():
            return float(r["LATITUDE"]), float(r["LONGITUDE"]), r.get("POSTAL", "")
    if res.get("results"):
        r = res["results"][0]
        return float(r["LATITUDE"]), float(r["LONGITUDE"]), r.get("POSTAL", "")
    return None


def main():
    rows = download_property_info()
    # Every HDB block, residential or not, is in scope of "every HDB block";
    # keep the residential flag so the dashboard can filter.
    blocks = [r for r in rows if r.get("residential") == "Y"]
    print(f"{len(rows)} properties, {len(blocks)} residential blocks", flush=True)

    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            cache = json.load(f)

    done = 0
    t0 = time.time()
    for i, b in enumerate(blocks):
        key = f"{b['blk_no']} {b['street']}"
        if key in cache:
            continue
        try:
            cache[key] = geocode(key)
        except RuntimeError:
            cache[key] = None
        done += 1
        if done % 50 == 0:
            rate = done / max(time.time() - t0, 1)
            left = sum(1 for x in blocks if f"{x['blk_no']} {x['street']}" not in cache)
            print(f"geocoded {done} new ({i+1}/{len(blocks)}), "
                  f"{rate:.1f}/s, ~{left/max(rate,0.1)/60:.0f} min left", flush=True)
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f)
        time.sleep(0.24)  # stay under OneMap's 250 calls/min

    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f)

    out, misses = [], []
    for b in blocks:
        key = f"{b['blk_no']} {b['street']}"
        hit = cache.get(key)
        if not hit:
            misses.append(key)
            continue
        out.append({
            "blk": b["blk_no"],
            "street": b["street"],
            "lat": round(hit[0], 6),
            "lon": round(hit[1], 6),
            "postal": hit[2],
            "town": b.get("bldg_contract_town", ""),
            "units": int(b.get("total_dwelling_units") or 0),
            "year": b.get("year_completed", ""),
        })
    with open(OUT_PATH, "w") as f:
        json.dump(out, f)
    print(f"DONE: {len(out)} blocks written to {OUT_PATH}, {len(misses)} misses", flush=True)
    if misses:
        with open(os.path.join(DATA, "hdb_geocode_misses.json"), "w") as f:
            json.dump(misses, f, indent=1)


if __name__ == "__main__":
    main()
