#!/usr/bin/env python3
"""Fetch every DBS/POSB touchpoint (ATMs, branches, deposit machines...) by
loading the DBS branch locator in a real browser and recording the content-API
responses the page itself makes (Akamai blocks direct HTTP).

Output: data/dbs_raw.json {url: response_json, ...}
"""
import json
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

captured = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900})

        def on_response(resp):
            u = resp.url
            if "contentapi" in u or "branch" in u.lower() or "locator" in u.lower():
                try:
                    body = resp.json()
                except Exception:
                    return
                captured.append({"url": u, "status": resp.status, "body": body})
                print(f"captured {resp.status} {u[:120]}", flush=True)

        page.on("response", on_response)
        print("loading locator page...", flush=True)
        page.goto("https://www.dbs.com.sg/index/locator.page",
                  wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(8000)

        # Poke the UI in case data loads lazily (search box, tabs)
        for sel in ["text=Self-Service Banking", "text=ATM", "text=Cash Withdrawal"]:
            try:
                page.click(sel, timeout=3000)
                page.wait_for_timeout(4000)
            except Exception:
                pass

        browser.close()

    with open(os.path.join(DATA, "dbs_raw.json"), "w") as f:
        json.dump(captured, f)
    print(f"DONE: {len(captured)} API responses saved", flush=True)


if __name__ == "__main__":
    main()
