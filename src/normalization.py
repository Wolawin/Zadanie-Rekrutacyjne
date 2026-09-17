import re
import pandas as pd


STATION_PRODUCT_MAP = {
    "PB95": "PB95",
    "PB98": "PB98",
    "ON": "ON",
    "DIESEL": "ON",
    "LPG": "LPG",
}

SAP_PRODUCT_MAP = {
    "BENZYNA BEZOLOWIOWA 95": "PB95",
    "BENZYNA BEZOŁOWIOWA 95": "PB95",
    "BENZYNA BEZOLOWIOWA 98": "PB98",
    "BENZYNA BEZOŁOWIOWA 98": "PB98",
    "OLEJ NAPEDOWY": "ON",
    "OLEJ NAPĘDOWY": "ON",
    "GAZ LPG": "LPG",
}


def clean_text(value):
    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def parse_number(value):
    """
    Obsługuje m.in.:
    20000
    20000,0
    12000,0 l
    6481.14
    n/d
    """
    if pd.isna(value):
        return None

    text = str(value).strip().lower()

    if text in ("", "n/d", "nd", "none", "nan"):
        return None

    text = text.replace("\xa0", "")
    text = text.replace(" ", "")
    text = re.sub(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", "", text)

    # polski separator dziesiętny
    if "," in text and "." not in text:
        text = text.replace(",", ".")

    # przypadek typu 1.234,56
    elif "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "")
            text = text.replace(",", ".")

    try:
        return float(text)
    except Exception:
        return None


def parse_date(value):
    if pd.isna(value):
        return pd.NaT

    text = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            return pd.to_datetime(text, format=fmt)
        except Exception:
            pass

    return pd.NaT


def normalize_station_id(value):
    value = clean_text(value)

    if value is None:
        return None

    value = value.upper().replace("ST", "").strip()

    if not value.isdigit():
        return None

    return "ST" + value.zfill(4)


def normalize_station_product(value):
    value = clean_text(value)

    if value is None:
        return None

    value = value.upper().strip()
    value = re.sub(r"\s+", "", value)

    return STATION_PRODUCT_MAP.get(value)


def normalize_sap_product(value):
    value = clean_text(value)

    if value is None:
        return None

    value = value.upper().strip()
    value = re.sub(r"\s+", " ", value)

    return SAP_PRODUCT_MAP.get(value)


def create_quality_issue(
    source,
    issue_type,
    row_number,
    field,
    raw_value,
    reason,
    business_key=None,
):
    return {
        "source": source,
        "issue_type": issue_type,
        "row_number": row_number,
        "business_key": business_key,
        "field": field,
        "raw_value": raw_value,
        "reason": reason,
    }


def normalize_station(df):
    data = df.copy()

    quality = []

    # Zachowujemy numer wiersza ze źródła.
    data["_source_row"] = range(2, len(data) + 2)

    # --------------------------------------------------------
    # Dokładne duplikaty
    # --------------------------------------------------------

    business_columns = [
        "kod_stacji",
        "data",
        "produkt",
        "sprzedaż_[l]",
        "stan_pocz_[l]",
        "stan_konc_[l]",
        "przyjęto_dostawę_[l]",
    ]

    duplicated_mask = data.duplicated(
        subset=business_columns,
        keep="first",
    )

    for _, row in data[duplicated_mask].iterrows():
        quality.append(
            create_quality_issue(
                source="STATION",
                issue_type="EXACT_DUPLICATE",
                row_number=row["_source_row"],
                field="row",
                raw_value="exact duplicate",
                reason=(
                    "Exact duplicate row detected. "
                    "Duplicate excluded from reconciliation "
                    "to avoid double counting."
                ),
            )
        )

    # Usuwamy jedynie dodatkowe kopie.
    data = data[~duplicated_mask].copy()

    # --------------------------------------------------------
    # Normalizacja
    # --------------------------------------------------------

    data["station_id"] = data["kod_stacji"].apply(
        normalize_station_id
    )

    data["business_date"] = data["data"].apply(
        parse_date
    )

    data["product"] = data["produkt"].apply(
        normalize_station_product
    )

    data["sales_qty"] = data["sprzedaż_[l]"].apply(
        parse_number
    )

    data["opening_stock"] = data["stan_pocz_[l]"].apply(
        parse_number
    )

    data["closing_stock"] = data["stan_konc_[l]"].apply(
        parse_number
    )

    data["station_quantity"] = data[
        "przyjęto_dostawę_[l]"
    ].apply(parse_number)

    # --------------------------------------------------------
    # Data Quality - kluczowe pola
    # --------------------------------------------------------

    for _, row in data.iterrows():
        key_parts = []

        if row["station_id"]:
            key_parts.append(str(row["station_id"]))

        if not pd.isna(row["business_date"]):
            key_parts.append(
                row["business_date"].strftime("%Y-%m-%d")
            )

        if row["product"]:
            key_parts.append(str(row["product"]))

        business_key = "|".join(key_parts)

        if row["station_id"] is None:
            quality.append(
                create_quality_issue(
                    "STATION",
                    "INVALID_STATION",
                    row["_source_row"],
                    "kod_stacji",
                    row["kod_stacji"],
                    "Station code cannot be normalized.",
                    business_key,
                )
            )

        if pd.isna(row["business_date"]):
            quality.append(
                create_quality_issue(
                    "STATION",
                    "INVALID_DATE",
                    row["_source_row"],
                    "data",
                    row["data"],
                    "Date cannot be parsed.",
                    business_key,
                )
            )

        if row["product"] is None:
            quality.append(
                create_quality_issue(
                    "STATION",
                    "UNKNOWN_PRODUCT",
                    row["_source_row"],
                    "produkt",
                    row["produkt"],
                    "Product cannot be mapped to canonical product.",
                    business_key,
                )
            )

        if row["station_quantity"] is None:
            quality.append(
                create_quality_issue(
                    "STATION",
                    "INVALID_DELIVERY_QUANTITY",
                    row["_source_row"],
                    "przyjęto_dostawę_[l]",
                    row["przyjęto_dostawę_[l]"],
                    "Delivery quantity cannot be parsed.",
                    business_key,
                )
            )

        # Pola nie są kluczem uzgodnienia, ale ich problemów
        # również nie pomijamy.
        optional_numeric_fields = [
            ("sprzedaż_[l]", "sales_qty"),
            ("stan_pocz_[l]", "opening_stock"),
            ("stan_konc_[l]", "closing_stock"),
        ]

        for raw_field, normalized_field in optional_numeric_fields:
            raw_value = row[raw_field]

            if (
                clean_text(raw_value) is not None
                and row[normalized_field] is None
            ):
                quality.append(
                    create_quality_issue(
                        "STATION",
                        "INVALID_NUMERIC_VALUE",
                        row["_source_row"],
                        raw_field,
                        raw_value,
                        (
                            "Numeric value cannot be parsed. "
                            "The field is not used directly for "
                            "delivery reconciliation but is reported "
                            "as a data quality signal."
                        ),
                        business_key,
                    )
                )

    valid_mask = (
        data["station_id"].notna()
        & data["business_date"].notna()
        & data["product"].notna()
        & data["station_quantity"].notna()
    )

    valid = data[valid_mask].copy()

    # --------------------------------------------------------
    # Niejednoznaczny biznesowy klucz źródła
    # --------------------------------------------------------

    key_cols = [
        "station_id",
        "business_date",
        "product",
    ]

    duplicated_business_key = valid.duplicated(
        subset=key_cols,
        keep=False,
    )

    for _, row in valid[duplicated_business_key].iterrows():
        key = (
            f"{row['station_id']}|"
            f"{row['business_date'].strftime('%Y-%m-%d')}|"
            f"{row['product']}"
        )

        quality.append(
            create_quality_issue(
                "STATION",
                "DUPLICATE_BUSINESS_KEY",
                row["_source_row"],
                "station/date/product",
                key,
                (
                    "More than one station record exists for the same "
                    "station, date and product. Records will be "
                    "aggregated for reconciliation, but the condition "
                    "is reported because the source specification "
                    "states one row per station/day/product."
                ),
                key,
            )
        )

    quality_df = pd.DataFrame(quality)

    return valid, quality_df


def normalize_sap(df):
    data = df.copy()

    quality = []

    data["_source_row"] = range(2, len(data) + 2)

    data["document_id"] = data["nr_dokumentu"].apply(
        clean_text
    )

    data["station_id"] = data["zakład"].apply(
        normalize_station_id
    )

    data["business_date"] = data[
        "data_księgowania"
    ].apply(parse_date)

    data["product"] = data["materiał"].apply(
        normalize_sap_product
    )

    # REGUŁA BIZNESOWA:
    # używamy ilości rzeczywistej, NIE 15°C
    data["sap_quantity"] = data[
        "ilość_rzeczywista_[l]"
    ].apply(parse_number)

    data["status_normalized"] = (
        data["status"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # --------------------------------------------------------
    # Walidacja
    # --------------------------------------------------------

    for _, row in data.iterrows():
        key_parts = []

        if row["station_id"]:
            key_parts.append(str(row["station_id"]))

        if not pd.isna(row["business_date"]):
            key_parts.append(
                row["business_date"].strftime("%Y-%m-%d")
            )

        if row["product"]:
            key_parts.append(str(row["product"]))

        business_key = "|".join(key_parts)

        if row["document_id"] is None:
            quality.append(
                create_quality_issue(
                    "SAP",
                    "MISSING_DOCUMENT_ID",
                    row["_source_row"],
                    "nr_dokumentu",
                    row["nr_dokumentu"],
                    "SAP document number is missing.",
                    business_key,
                )
            )

        if row["station_id"] is None:
            quality.append(
                create_quality_issue(
                    "SAP",
                    "INVALID_STATION",
                    row["_source_row"],
                    "zakład",
                    row["zakład"],
                    "Plant/station cannot be normalized.",
                    business_key,
                )
            )

        if pd.isna(row["business_date"]):
            quality.append(
                create_quality_issue(
                    "SAP",
                    "INVALID_DATE",
                    row["_source_row"],
                    "data_księgowania",
                    row["data_księgowania"],
                    "Posting date cannot be parsed.",
                    business_key,
                )
            )

        if row["product"] is None:
            quality.append(
                create_quality_issue(
                    "SAP",
                    "UNKNOWN_PRODUCT",
                    row["_source_row"],
                    "materiał",
                    row["materiał"],
                    "SAP material cannot be mapped to canonical product.",
                    business_key,
                )
            )

        if row["sap_quantity"] is None:
            quality.append(
                create_quality_issue(
                    "SAP",
                    "INVALID_QUANTITY",
                    row["_source_row"],
                    "ilość_rzeczywista_[l]",
                    row["ilość_rzeczywista_[l]"],
                    "Actual SAP quantity cannot be parsed.",
                    business_key,
                )
            )

        if row["status_normalized"] not in ("UTW", "STO"):
            quality.append(
                create_quality_issue(
                    "SAP",
                    "UNKNOWN_SAP_STATUS",
                    row["_source_row"],
                    "status",
                    row["status"],
                    (
                        "Unknown SAP status. Record excluded from "
                        "active-delivery reconciliation."
                    ),
                    business_key,
                )
            )

    # --------------------------------------------------------
    # Duplikaty nr dokumentu
    # --------------------------------------------------------

    duplicate_doc_mask = (
        data["document_id"].notna()
        & data.duplicated(
            subset=["document_id"],
            keep=False,
        )
    )

    duplicate_document_ids = set(
        data.loc[
            duplicate_doc_mask,
            "document_id"
        ].tolist()
    )

    for _, row in data[duplicate_doc_mask].iterrows():
        key = ""

        if (
            row["station_id"] is not None
            and not pd.isna(row["business_date"])
            and row["product"] is not None
        ):
            key = (
                f"{row['station_id']}|"
                f"{row['business_date'].strftime('%Y-%m-%d')}|"
                f"{row['product']}"
            )

        quality.append(
            create_quality_issue(
                "SAP",
                "DUPLICATE_DOCUMENT_ID",
                row["_source_row"],
                "nr_dokumentu",
                row["document_id"],
                (
                    "SAP document number occurs more than once although "
                    "the input specification states one row per delivery "
                    "document. Rows are excluded from reconciliation "
                    "because their meaning is ambiguous."
                ),
                key,
            )
        )

    base_valid = (
        data["document_id"].notna()
        & data["station_id"].notna()
        & data["business_date"].notna()
        & data["product"].notna()
        & data["sap_quantity"].notna()
        & data["status_normalized"].isin(["UTW", "STO"])
        & ~data["document_id"].isin(duplicate_document_ids)
    )

    valid = data[base_valid].copy()

    quality_df = pd.DataFrame(quality)

    return valid, quality_df
