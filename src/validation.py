import pandas as pd
from pathlib import Path


def read_csv_flexible(path: Path) -> pd.DataFrame:
    """
    Próbuje wczytać CSV z najczęściej spotykanymi separatorami i kodowaniami.
    Nie zakładamy z góry spójnego formatu plików.
    """
    attempts = [
        {"sep": ";", "encoding": "utf-8-sig"},
        {"sep": ",", "encoding": "utf-8-sig"},
        {"sep": ";", "encoding": "cp1250"},
        {"sep": ",", "encoding": "cp1250"},
        {"sep": "\t", "encoding": "utf-8-sig"},
    ]

    last_error = None

    for options in attempts:
        try:
            df = pd.read_csv(path, **options)

            # Jeżeli wyszła tylko jedna kolumna, separator prawdopodobnie jest zły
            if len(df.columns) > 1:
                print(
                    f"Loaded {path.name} "
                    f"using separator={repr(options['sep'])}, "
                    f"encoding={options['encoding']}"
                )
                return df

        except Exception as exc:
            last_error = exc

    raise ValueError(
        f"Unable to read file {path}. Last error: {last_error}"
    )


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizuje wyłącznie nazwy kolumn.
    Nie zmienia jeszcze danych biznesowych.
    """
    result = df.copy()

    result.columns = (
        result.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace(".", "_", regex=False)
        .str.replace(r"_+", "_", regex=True)
    )

    return result


def profile_dataframe(df: pd.DataFrame, source_name: str) -> dict:
    print("\n" + "=" * 80)
    print(f"DATA PROFILE: {source_name}")
    print("=" * 80)

    print(f"\nRows: {len(df)}")
    print(f"Columns: {len(df.columns)}")

    print("\nColumn names:")
    for column in df.columns:
        print(f" - {column}")

    print("\nData types:")
    print(df.dtypes.to_string())

    print("\nMissing values:")
    missing = df.isna().sum().sort_values(ascending=False)
    print(missing.to_string())

    duplicate_count = df.duplicated().sum()

    print(f"\nExact duplicate rows: {duplicate_count}")

    print("\nSample records:")
    print(df.head(10).to_string())

    print("\nUnique values overview:")

    for column in df.columns:
        unique_count = df[column].nunique(dropna=True)

        print(
            f"{column}: "
            f"{unique_count} unique values"
        )

        if unique_count <= 20:
            values = (
                df[column]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()
            )
            print(f"  Values: {values}")

    result = {
        "source": source_name,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "duplicate_rows": int(duplicate_count),
        "missing_values": missing.to_dict(),
    }

    return result


def validate_required_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Required input file does not exist: {path}"
        )

    if path.stat().st_size == 0:
        raise ValueError(
            f"Input file is empty: {path}"
        )


def load_and_profile(path: Path, source_name: str):
    validate_required_file(path)

    raw_df = read_csv_flexible(path)
    df = normalize_column_names(raw_df)

    profile = profile_dataframe(df, source_name)

    return df, profile

