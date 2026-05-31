"""
UREC Occupancy Scraper — University of Alabama Recreation Center
API Provider : GoBoard (goboardapi.azurewebsites.net)
Response Format: XML (ArrayOfCountLocationResponseModel)
Schedule      : Hourly via GitHub Actions (collect.yml)

Confirmed XML fields (from live API response):
  FacilityId, FacilityName, LocationId, LocationName,
  IsClosed, LastCount, TotalCapacity, PercetageCapacity,
  LastUpdatedDateAndTime
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

        last_count    = int(get("LastCount") or 0)
        total_cap     = int(get("TotalCapacity") or 0)

        # PercetageCapacity in the API is always 0; compute it correctly here
        occupancy_pct = (
            round(last_count / total_cap * 100, 1) if total_cap > 0 else 0.0
        )

        rows.append({
            "facility_id":      get("FacilityId"),
            "facility_name":    get("FacilityName"),
            "location_id":      get("LocationId"),
            "location_name":    get("LocationName"),
            "is_closed":        get("IsClosed"),          # "true" / "false"
            "last_count":       last_count,
            "total_capacity":   total_cap,
            "occupancy_pct":    occupancy_pct,
            "last_updated_api": get("LastUpdatedDateAndTime"),
        })

    return rows


def ensure_csv_exists():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def append_rows(rows: list[dict]):
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    now_utc   = now_local.astimezone(ZoneInfo("UTC"))
    ensure_csv_exists()

    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        for row in rows:
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
        f"[OK] {len(rows)} locations saved at "
        f"{now_local.isoformat(timespec='seconds')} (local)."
    )


def main():
    xml_text = fetch_xml()
    rows     = parse_xml(xml_text)
    append_rows(rows)


if __name__ == "__main__":
    main()