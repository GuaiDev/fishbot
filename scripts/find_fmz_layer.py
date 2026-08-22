"""Locate Ontario's Fisheries Management Zone layer across the LIO services.

The FMZ adapter was pointed at LIO_Open06, which turns out to hold Greenbelt
and land-use planning layers. Rather than guess again, this walks the LIO
OPEN_DATA folder, lists every service and layer, and reports anything that
looks like fisheries zones. Read-only; prints candidates, changes nothing.

    uv run python scripts/find_fmz_layer.py
"""

import sys

import httpx

ROOT = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA"
UA = {"User-Agent": "fishbot/1.0 (personal fishing exploration bot)"}
HINTS = ("fisheries management", "fmz", "fishing zone", "fisheries")


def main() -> int:
    try:
        r = httpx.get(f"{ROOT}?f=json", timeout=60, headers=UA)
        r.raise_for_status()
        services = [s["name"] for s in r.json().get("services", [])]
    except Exception as exc:
        print(f"Could not list services: {type(exc).__name__}: {exc}")
        return 1

    print(f"{len(services)} services under LIO_OPEN_DATA\n")
    hits = []

    for svc in services:
        url = f"https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/{svc}/MapServer?f=json"
        try:
            resp = httpx.get(url, timeout=60, headers=UA)
            resp.raise_for_status()
            layers = resp.json().get("layers", [])
        except Exception as exc:
            print(f"  {svc}: unreachable ({type(exc).__name__})")
            continue

        for lyr in layers:
            name = str(lyr.get("name", ""))
            if any(h in name.lower() for h in HINTS):
                hits.append((svc, lyr.get("id"), name))
                print(f"  MATCH  {svc}  layer {lyr.get('id')}  {name!r}")

    print()
    if hits:
        print("Candidates found. Give these to Claude to point the adapter at:")
        for svc, lid, name in hits:
            print(f"   service={svc}  layer_id={lid}  name={name!r}")
    else:
        print("No fisheries layer found in LIO_OPEN_DATA.")
        print("The FMZ boundaries may be published elsewhere — try Ontario GeoHub")
        print("(geohub.lio.gov.on.ca) and search 'Fisheries Management Zone'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
