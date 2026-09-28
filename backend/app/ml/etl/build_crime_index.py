"""One-off ETL: rebuild app/data/reference/ncrb_crime_against_foreigners.json
from the source NCRB/Mendeley spreadsheet.

Not run in CI or at request time (excluded from coverage, see pyproject.toml)
-- this is a manual, occasional step whose OUTPUT is the committed artifact
the app actually reads (app/services/crime_index.py). Run it again only when
a newer year of NCRB data is compiled into the same Mendeley dataset.

Source: "Crime against Foreigners in India 2014-2021", NCRB, Ministry of Home
Affairs GoI (Chapter 13A of "Crime in India"), FTA figures from the Ministry
of Tourism GoI, compiled by Vishal Tikhute and distributed via Mendeley Data:
https://data.mendeley.com/datasets/tyzj3j83gj/1 (DOI 10.17632/tyzj3j83gj.1)

Usage:
    python -m app.ml.etl.build_crime_index path/to/downloaded.xlsx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[2] / "data" / "reference" / "ncrb_crime_against_foreigners.json"

# Years where FTA collapsed due to COVID-19 travel restrictions, making the
# crime RATE (cases / FTA) misleading as a risk signal -- the denominator
# shrank far more than any genuine change in risk to tourists. Excluded from
# the pre-COVID baseline in app/services/crime_index.py.
COVID_ANOMALOUS_YEARS = {2020, 2021}


def build(xlsx_path: str) -> dict:
    import openpyxl  # dev-only dependency; not needed at runtime

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Crime Incidence and rate"]

    series = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        year = row[0]
        if not isinstance(year, int):
            continue  # skips the trailing footnote row
        entry = {
            "year": year,
            "cases_registered": int(row[1]),
            "fta_million": float(row[2]),
            "crime_rate_per_lakh_fta": round(float(row[3]), 4),
        }
        if year in COVID_ANOMALOUS_YEARS:
            entry["covid_anomalous"] = True
        series.append(entry)

    return {
        "_meta": {
            "title": "Crime against Foreigners in India, 2014-2021",
            "source": (
                "National Crime Records Bureau (NCRB), Ministry of Home Affairs, "
                "GoI. Chapter 13A of the annual 'Crime in India' report. FTA "
                "(foreign tourist arrivals) from the Ministry of Tourism, GoI."
            ),
            "compiled_by": "Vishal Tikhute, distributed via Mendeley Data",
            "url": "https://data.mendeley.com/datasets/tyzj3j83gj/1",
            "doi": "10.17632/tyzj3j83gj.1",
            "granularity": "national (India-wide), annual",
            "note": (
                "No state/UT-wise breakdown of this series is available without "
                "a data.gov.in API key -- see app/services/crime_index.py for how "
                "this national series is used as a calibration anchor rather than "
                "a per-state lookup. 2020-2021 crime RATE spikes are a COVID-19 "
                "artifact and are excluded from the pre-COVID baseline."
            ),
        },
        "series": series,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    data = build(sys.argv[1])
    OUTPUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(data['series'])} years)")
