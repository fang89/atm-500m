#!/usr/bin/env python3
"""Fetch DBS/POSB Cash-Point participating merchant outlets.

Per posb.com.sg/personal/deposits/bank-with-ease/cash-point (checked Jul 2026):
  up to S$200: 7-Eleven, Giant, Cold Storage, Jasons Deli
  up to S$100: Guardian, buzz
  excluded: Changi Airport outlets; Sheng Siong/Haomart/U Stars left the
  scheme on 1 Nov 2025. buzz (a handful of SingPost pods) is omitted here.

Sources:
  Giant / Cold Storage / Jasons  -> NEA licensed-supermarkets dataset
                                    (data/nea_supermarkets.json) + OneMap postal geocode
  7-Eleven / Guardian            -> OpenStreetMap Overpass API (ODbL)

Output: data/cashpoints.json [{name, addr, lat, lon, chain, limit}]
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "cashpoints.json")
CACHE = os.path.join(DATA, "postal_geocode_cache.json")

OVERPASS = "https://overpass.kumi.systems/api/interpreter"
ONEMAP = "https://www.onemap.gov.sg/api/common/elastic/search"

NEA_CHAINS = {  # business_name match -> (chain label, withdrawal limit)
    "GIANT": ("Giant", 200),
    "COLD STORAGE": ("Cold Storage", 200),
    "JASONS": ("Jasons Deli", 200),
}


def http_json(url, data=None, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except Exception as e:
            print(f"  retry {i+1}: {e}", flush=True)
            time.sleep(3 * (i + 1))
    raise RuntimeError(url)


def geocode_postal(postal, cache):
    if postal in cache:
        return cache[postal]
    q = urllib.parse.quote(postal)
    res = http_json(f"{ONEMAP}?searchVal={q}&returnGeom=Y&getAddrDetails=Y&pageNum=1")
    hit = None
    for r in res.get("results", []):
        if r.get("POSTAL") == postal:
            hit = (float(r["LATITUDE"]), float(r["LONGITUDE"]))
            break
    cache[postal] = hit
    time.sleep(0.9)  # shared OneMap throttle (block-enrichment job may be running)
    return hit


def from_nea():
    rows = json.load(open(os.path.join(DATA, "nea_supermarkets.json")))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    out, miss = [], 0
    todo = []
    for r in rows:
        name = r["business_name"].upper()
        for key, (chain, limit) in NEA_CHAINS.items():
            if key in name:
                todo.append((r, chain, limit))
                break
    print(f"NEA outlets to geocode: {len(todo)}", flush=True)
    for i, (r, chain, limit) in enumerate(todo):
        m = re.search(r"S\((\d{6})\)", r["premise_address"])
        if not m:
            miss += 1
            continue
        pos = geocode_postal(m.group(1), cache)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
            json.dump(cache, open(CACHE, "w"))
        if not pos:
            miss += 1
            continue
        out.append({"name": r["business_name"].title(),
                    "addr": r["premise_address"].title(),
                    "lat": round(pos[0], 6), "lon": round(pos[1], 6),
                    "chain": chain, "limit": limit})
    json.dump(cache, open(CACHE, "w"))
    print(f"NEA: {len(out)} geocoded, {miss} missed", flush=True)
    return out


def from_osm():
    query = """
[out:json][timeout:240];
area["ISO3166-1"="SG"][admin_level=2]->.sg;
(
  nwr["shop"]["name"~"7-Eleven",i](area.sg);
  nwr["shop"]["brand"~"7-Eleven",i](area.sg);
  nwr["shop"~"chemist|health_and_beauty"]["name"~"^Guardian",i](area.sg);
  nwr["shop"~"chemist|health_and_beauty"]["brand"~"^Guardian",i](area.sg);
);
out center tags;
"""
    osm_cache = os.path.join(DATA, "osm_cashpoints.json")
    if os.path.exists(osm_cache):
        res = json.load(open(osm_cache))
    else:
        res = http_json(OVERPASS, data=urllib.parse.urlencode({"data": query}).encode())
        json.dump(res, open(osm_cache, "w"))
    out, seen = [], set()
    for el in res.get("elements", []):
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None:
            continue
        name = tags.get("name", "") or tags.get("brand", "")
        is7 = "7-eleven" in (name + tags.get("brand", "")).lower()
        chain = "7-Eleven" if is7 else "Guardian"
        # commitment excludes Changi Airport outlets
        addr = " ".join(tags.get(k, "") for k in
                        ("addr:housenumber", "addr:street", "addr:unit", "addr:postcode"))
        blob = (name + " " + addr).lower()
        if "changi airport" in blob or "airport boulevard" in blob:
            continue
        key = (round(lat, 5), round(lon, 5), chain)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name or chain, "addr": addr.strip(),
                    "lat": round(lat, 6), "lon": round(lon, 6),
                    "chain": chain, "limit": 200 if is7 else 100})
    n7 = sum(1 for o in out if o["chain"] == "7-Eleven")
    print(f"OSM: {n7} 7-Eleven, {len(out)-n7} Guardian", flush=True)
    return out


def main():
    pts = from_osm() + from_nea()
    json.dump(pts, open(OUT, "w"))
    print(f"DONE: {len(pts)} cashpoints -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
