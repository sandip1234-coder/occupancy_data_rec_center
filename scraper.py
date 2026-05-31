"""
UREC Occupancy Scraper — University of Alabama Recreation Center
API Provider : GoBoard (goboardapi.azurewebsites.net)
Response Format: XML (ArrayOfCountLocationResponseModel)
Schedule      : Hourly via GitHub Actions (collect.yml)

Behaviour:
  - Fetches live occupancy counts from the GoBoard API
  - Skips writing rows if the sensor timestamp has not changed since last scrape
  - Appends only genuinely new readings to data/occupancy.csv
  - Preserves both scrape timestamp and sensor timestamp for research transparency
"""

import csv
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# ── Configuration ──────────────────────────────────────────────────────────────
API_ENDPOINT = (
    "https://goboardapi.azurewebsites.net/api/FacilityCount/GetCountsByAccount"
    "?AccountAPIKey=af686e9b-7ace-49a0-b6b5-af09c7a4278b"
)

DATA_FILE = "data/occupancy.csv"
TIMEZONE  = "America/Chicago"

FIELDNAMES = [
    "timestamp_local",
    "timestamp_utc",
    "facility_id",
    "facility_name",
    "location_id",
    "location_name",
    "is_closed",
    "last_count",
    "total_capacity",
    "occupancy_pct",
    "last_updated_api",
    "source_url",
]

# XML namespace declared in the API response root element
NS = {
    "g": "http://schemas.datacontract.org/2004/07/GoBoard.WebApi.Models",
    "i": "http://www.w3.org/2001/XMLSchema-instance",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; UREC-occupancy-research-bot/1.0; "
        "contact: your-email@ua.edu)"
    ),
    "Accept": "application/xml, text/xml",
}
# ──────────────────────────────────────────────────────────────────────────────


def fetch_xml() -> str:
    resp = requests.get(API_ENDPOINT, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []

    for model in root.findall("g:CountLocationResponseModel", NS):

        def get(tag: str) -> str:
            el = model.find(f"g:{tag}", NS)
            if el is None:
                return ""
            nil = el.attrib.get(
                "{http://www.w3.org/2001/XMLSchema-instance}nil", "false"
            )
            return "" if nil == "true" else (el.text or "").strip()

        last_count = int(get("LastCount") or 0)
        total_cap  = int(get("TotalCapacity") or 0)

        # PercetageCapacity in the API is always 0; compute correctly here
        occupancy_pct = (
            round(last_count / total_cap * 100, 1) if total_cap > 0 else 0.0
        )

        rows.append({
            "facility_id":      get("FacilityId"),
            "facility_name":    get("FacilityName"),
            "location_id":      get("LocationId"),
            "location_name":    get("LocationName"),
            "is_closed":        get("IsClosed"),
            "last_count":       last_count,
            "total_capacity":   total_cap,
            "occupancy_pct":    occupancy_pct,
            "last_updated_api": get("LastUpdatedDateAndTime"),
        })

    return rows


def get_last_recorded_timestamps() -> dict:
    """
    Read the CSV and return a dict of {location_id: last_updated_api}
    so we can compare against the new API response and skip duplicates.
    """
    if not os.path.exists(DATA_FILE):
        return {}

    last_seen = {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            last_seen[row["location_id"]] = row["last_updated_api"]
    return last_seen


def ensure_csv_exists():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def append_rows(rows: list[dict], last_seen: dict):
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    now_utc   = now_local.astimezone(ZoneInfo("UTC"))
    ensure_csv_exists()

    new_rows = []
    for row in rows:
        loc_id      = str(row["location_id"])
        api_updated = row["last_updated_api"]

        # Only save if this location has a genuinely new sensor reading
        if last_seen.get(loc_id) == api_updated:
            print(f"[SKIP] {row['location_name']} — no new data since {api_updated}")
            continue

        new_rows.append(row)

    if not new_rows:
        print("[OK] No new data across any location. Nothing written.")
        return

    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        for row in new_rows:
            writer.writerow({
                "timestamp_local":  now_local.isoformat(timespec="seconds"),
                "timestamp_utc":    now_utc.isoformat(timespec="seconds"),
                "facility_id":      row["facility_id"],
                "facility_name":    row["facility_name"],
                "location_id":      row["location_id"],
                "location_name":    row["location_name"],
                "is_closed":        row["is_closed"],
                "last_count":       row["last_count"],
                "total_capacity":   row["total_capacity"],
                "occupancy_pct":    row["occupancy_pct"],
                "last_updated_api": row["last_updated_api"],
                "source_url":       API_ENDPOINT,
            })

    print(
        f"[OK] {len(new_rows)} new rows saved at "
        f"{now_local.isoformat(timespec='seconds')} (local)."
    )


def main():
    xml_text  = fetch_xml()
    rows      = parse_xml(xml_text)
    last_seen = get_last_recorded_timestamps()
    append_rows(rows, last_seen)


if __name__ == "__main__":
    main()