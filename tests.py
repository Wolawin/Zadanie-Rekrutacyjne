import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"

sys.path.insert(0, str(SRC_DIR))

from reconciliation import tolerance_for, reconcile


def test_tolerance_minimum_50():
    assert tolerance_for(5000) == 50.0


def test_tolerance_percentage():
    assert tolerance_for(24000) == 120.0


def test_quantity_match_inside_tolerance():
    station = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "PB95",
            "station_quantity": 10000.0,
            "_source_row": 2,
        }
    ])

    sap = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "PB95",
            "sap_quantity": 10040.0,
            "document_id": "DOC1",
            "status_normalized": "UTW",
            "_source_row": 2,
        }
    ])

    result, _, _, _ = reconcile(station, sap)

    assert len(result) == 1
    assert result.iloc[0]["category"] == "MATCH"


def test_quantity_difference():
    station = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "PB95",
            "station_quantity": 10000.0,
            "_source_row": 2,
        }
    ])

    sap = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "PB95",
            "sap_quantity": 12000.0,
            "document_id": "DOC1",
            "status_normalized": "UTW",
            "_source_row": 2,
        }
    ])

    result, _, _, _ = reconcile(station, sap)

    assert result.iloc[0]["category"] == "QUANTITY_DIFFERENCE"


def test_date_shift():
    station = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "ON",
            "station_quantity": 20000.0,
            "_source_row": 2,
        }
    ])

    sap = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-25"),
            "product": "ON",
            "sap_quantity": 20000.0,
            "document_id": "DOC1",
            "status_normalized": "UTW",
            "_source_row": 2,
        }
    ])

    result, _, _, _ = reconcile(station, sap)

    assert len(result) == 1
    assert result.iloc[0]["category"] == "DATE_SHIFT"


def test_sto_not_match():
    station = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "PB98",
            "station_quantity": 12000.0,
            "_source_row": 2,
        }
    ])

    sap = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "PB98",
            "sap_quantity": 12000.0,
            "document_id": "DOC1",
            "status_normalized": "STO",
            "_source_row": 2,
        }
    ])

    result, _, _, _ = reconcile(station, sap)

    assert result.iloc[0]["category"] == "STATION_WITH_STO"


def test_multiple_sap_documents_are_aggregated():
    station = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "LPG",
            "station_quantity": 24000.0,
            "_source_row": 2,
        }
    ])

    sap = pd.DataFrame([
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "LPG",
            "sap_quantity": 12000.0,
            "document_id": "DOC1",
            "status_normalized": "UTW",
            "_source_row": 2,
        },
        {
            "station_id": "ST0001",
            "business_date": pd.Timestamp("2026-08-24"),
            "product": "LPG",
            "sap_quantity": 12000.0,
            "document_id": "DOC2",
            "status_normalized": "UTW",
            "_source_row": 3,
        },
    ])

    result, _, _, _ = reconcile(station, sap)

    assert len(result) == 1
    assert result.iloc[0]["category"] == "MATCH"
    assert result.iloc[0]["sap_quantity"] == 24000.0


TESTS = [
    test_tolerance_minimum_50,
    test_tolerance_percentage,
    test_quantity_match_inside_tolerance,
    test_quantity_difference,
    test_date_shift,
    test_sto_not_match,
    test_multiple_sap_documents_are_aggregated,
]


def main():
    passed = 0

    print("=" * 70)
    print("AUTOMATED BUSINESS RULE TESTS")
    print("=" * 70)

    for test in TESTS:
        try:
            test()
            passed += 1
            print(f"PASS  {test.__name__}")
        except Exception as exc:
            print(f"FAIL  {test.__name__}")
            print(f"      {exc}")

    print()
    print(f"Result: {passed}/{len(TESTS)} tests passed")

    if passed != len(TESTS):
        sys.exit(1)


if __name__ == "__main__":
    main()

