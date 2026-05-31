"""
UREC Historical Occupancy Fetcher
Run once manually to attempt bulk retrieval of historical data from GoBoard API.
Results saved to data/occupancy_historical.csv
"""

import csv
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

API_KEY = "af686e9b-7ace-49a0-b6b5-af09c7a4278b"
BASE    = "https://goboardapi.azurewebsites.net/api/FacilityCount"

# All confirmed location IDs from the live API
LOCATIONS = {
    6627:  "SRC Weight Room",
    6628:  "SRC Cardio",
    10605: 'Resistance Training Room "RTR"',
    6866:  "Indoor Pool",
    6861:  "SRC South Gym",
    6862:  "SRC North Gym",
    6625:  "Tennis Courts",
    6864:  "SRC Racquetball Courts",
    6632:  "Witt Basketball Courts",
    6636:  "Witt Weight Room",
    6633:  "Witt Multipurpose Court",
    6637:  "Witt Cardio",
    6635:  "Witt Mezzanine Cardio",
}

NS = {"g": "http://schemas.datacontract.org/2004/07/GoBoard.WebApi.Models"}

FIELDNAMES = [
    "location_id", "location_name",
    "last_count", "total_capacity", "occupancy_pct",
    "last_updated_api",
]

OUT_FILE = "data/occupancy_historical.csv"

HEADERS = {
    "User-Agent": "UREC-occupancy-research-bot/1.0; contact: your-email@ua.edu",
    "Accept": "application/xml, text/xml",
}

# ── Endpoint patterns to attempt ──────────────────────────────────────────────
ENDPOINT_TEMPLATES = [
    BASE + "/GetCountsByLocation?LocationId={loc_id}&StartDate={start}&EndDate={end}",
    BASE + "/GetHistoricalCounts?LocationId={loc_id}&StartDate={start}&EndDate={end}&AccountAPIKey={key}",
    BASE + "/GetHistoricalCountsByLocation?LocationId={loc_id}&StartDate={start}&EndDate={end}&AccountAPIKey={key}",
]

START_DATE = "2023-01-01"
END_DATE   = datetime.now().strftime("%Y-%m-%d")
# ──────────────────────────────────────────────────────────────────────────────


def try_fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200 and len(resp.text) > 100:
            return resp.text
    except Exception as exc:
        print(f"  [FAIL] {exc}")
    return None


def parse_historical_xml(xml_text: str, loc_id: int) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []
    for model in root.iter():
        if "CountLocationResponseModel" not in model.tag:
            continue

        def get(tag):
            el = model.find(f"g:{tag}", NS)
            return "" if el is None else (el.text or "").strip()

        last_count  = int(get("LastCount") or 0)
        total_cap   = int(get("TotalCapacity") or 0)
        occ_pct     = round(last_count / total_cap * 100, 1) if total_cap > 0 else 0.0

        rows.append({
            "location_id":      loc_id,
            "location_name":    LOCATIONS.get(loc_id, "Unknown"),
            "last_count":       last_count,
            "total_capacity":   total_cap,
            "occupancy_pct":    occ_pct,
            "last_updated_api": get("LastUpdatedDateAndTime"),
        })
    return rows


def main():
    os.makedirs("data", exist_ok=True)
    all_rows = []

    for loc_id, loc_name in LOCATIONS.items():
        print(f"\nFetching: {loc_name} (ID {loc_id})")
        found = False

        for template in ENDPOINT_TEMPLATES:
            url = template.format(
                loc_id=loc_id, start=START_DATE, end=END_DATE, key=API_KEY
            )
            print(f"  Trying: {url[:90]}...")
            xml_text = try_fetch(url)

            if xml_text:
                rows = parse_historical_xml(xml_text, loc_id)
                if rows:
                    print(f"  [OK] {len(rows)} historical records retrieved.")
                    all_rows.extend(rows)
                    found = True
                    break

        if not found:
            print(f"  [NONE] No historical data available for {loc_name}.")

    if all_rows:
        with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n[DONE] {len(all_rows)} total rows saved to {OUT_FILE}")
    else:
        print("\n[RESULT] No historical data was accessible via any known endpoint.")
        print("         Begin forward collection immediately via the hourly scraper.")


if __name__ == "__main__":
    main()