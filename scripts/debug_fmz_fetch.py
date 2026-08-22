"""Show exactly what the FMZ layer returns. Prints directly — no logging config.

    uv run python scripts/debug_fmz_fetch.py
"""

import json
import sys

import httpx

ROOT = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest"
    "/services/LIO_OPEN_DATA/LIO_Open07/MapServer"
)
UA = {"User-Agent": "fishbot/1.0 (personal fishing exploration bot)"}


def show(label: str, r: httpx.Response) -> dict | None:
    print(f"\n--- {label} ---")
    print(f"    HTTP {r.status_code}   content-type: {r.headers.get('content-type')}")
    print(f"    bytes: {len(r.content):,}")
    try:
        payload = r.json()
    except ValueError:
        print(f"    NOT JSON. First 300 chars:\n      {' '.join(r.text[:300].split())}")
        return None
    if isinstance(payload, dict) and payload.get("error"):
        print(f"    Esri error: {json.dumps(payload['error'])[:300]}")
        return None
    feats = payload.get("features", []) if isinstance(payload, dict) else []
    print(f"    features: {len(feats)}   exceededTransferLimit: "
          f"{payload.get('exceededTransferLimit')}")
    if feats:
        f0 = feats[0]
        attrs = f0.get("attributes") or f0.get("properties") or {}
        print(f"    FIELD NAMES: {sorted(attrs)}")
        print(f"    first feature attrs: {json.dumps(attrs)[:300]}")
        g = f0.get("geometry") or {}
        print(f"    geometry keys: {sorted(g)[:6]}")
    return payload


def main() -> int:
    print("=== layer 14 metadata ===")
    r = httpx.get(f"{ROOT}/14?f=json", timeout=60, headers=UA)
    try:
        meta = r.json()
        print(f"    name: {meta.get('name')!r}   type: {meta.get('type')}")
        print(f"    maxRecordCount: {meta.get('maxRecordCount')}")
        print(f"    fields: {[f['name'] for f in meta.get('fields', [])]}")
    except ValueError:
        print(f"    metadata not JSON: {' '.join(r.text[:200].split())}")

    base = {"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326"}

    # count only — cheap, proves the query works at all
    r = httpx.get(f"{ROOT}/14/query",
                  params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                  timeout=60, headers=UA)
    show("count only (f=json)", r)

    for label, extra in (
        ("f=json, generalised", {"f": "json", "maxAllowableOffset": "0.002"}),
        ("f=json, full detail", {"f": "json"}),
        ("f=geojson", {"f": "geojson"}),
    ):
        try:
            r = httpx.get(f"{ROOT}/14/query", params={**base, **extra},
                          timeout=300, headers=UA)
            show(label, r)
        except Exception as exc:
            print(f"\n--- {label} ---\n    REQUEST FAILED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
