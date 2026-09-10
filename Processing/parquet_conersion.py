import os, re, calendar
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def clean_date(v):
    if pd.isna(v):
        return pd.NA
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null", "nat", "<na>"}:
        return pd.NA

    s = re.split(r"[T\s]", s, 1)[0].replace("/", "-").replace(".", "-")
    s = re.sub(r"[^0-9-]", "", s)

    for p, typ in [
        (r"^(\d{4})-(\d{1,2})-(\d{1,2})$", "ymd"),
        (r"^(\d{1,2})-(\d{1,2})-(\d{4})$", "dmy"),
        (r"^(\d{1,2})-(\d{1,2})-(\d{2})$", "dmy2"),
    ]:
        m = re.fullmatch(p, s)
        if not m:
            continue
        a, b, c = map(int, m.groups())
        if typ == "ymd":
            y, mo, d = a, b, c
        elif typ == "dmy":
            d, mo, y = a, b, c
        else:
            d, mo, y = a, b, 2000 + c if c <= 50 else 1900 + c
        try:
            if 1 <= mo <= 12 and 1 <= d <= calendar.monthrange(y, mo)[1]:
                return f"{y:04d}-{mo:02d}-{d:02d}"
        except ValueError:
            pass
    return pd.NA


def convert_csv_to_parquet(input_file, output_file, date_cols=None,
                            chunksize=50_000, compression="snappy"):
    """
    Convert a CSV or Excel file to Parquet, normalizing given date columns
    to YYYY-MM-DD strings. Tries utf-8-sig first, falls back to cp1252 for CSVs.

    Returns a dict with rows, columns, row_groups for a quick summary.
    """
    date_cols = date_cols or []
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    if os.path.isfile(output_file):
        os.remove(output_file)

    # Check if input is an Excel file
    if str(input_file).lower().endswith((".xlsx", ".xls")):
        print(f"Reading Excel file: {input_file} ...")
        df = pd.read_excel(input_file, dtype=str, engine="openpyxl")
        for col in date_cols:
            if col in df.columns:
                df[col] = df[col].map(clean_date).astype("string")
            else:
                print(f"Warning: Date column '{col}' not found in file columns.")

        table = pa.Table.from_pandas(df.astype("string"), preserve_index=False)
        pq.write_table(table, output_file, compression=compression)
        print(f"Converted Excel to Parquet: {len(df):,} rows")
    else:
        # CSV file (chunked)
        def _run(enc):
            writer, total = None, 0
            try:
                for i, df in enumerate(pd.read_csv(
                    input_file, dtype=str, encoding=enc,
                    chunksize=chunksize, low_memory=True
                ), 1):
                    for col in date_cols:
                        if col in df.columns:
                            df[col] = df[col].map(clean_date).astype("string")
                        else:
                            print(f"Warning: Date column '{col}' not found in file columns.")

                    table = pa.Table.from_pandas(df.astype("string"), preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(output_file, table.schema, compression=compression)
                    writer.write_table(table)
                    total += len(df)
                    print(f"Chunk {i} | Rows: {total:,}")
            finally:
                if writer:
                    writer.close()

        try:
            _run("utf-8-sig")
        except UnicodeDecodeError:
            print("UTF-8 failed -> retrying cp1252")
            if os.path.isfile(output_file):
                os.remove(output_file)
            _run("cp1252")

    import time
    for _ in range(5):
        try:
            p = pq.ParquetFile(output_file)
            return {
                "output_file": output_file,
                "rows": p.metadata.num_rows,
                "columns": p.metadata.num_columns,
                "row_groups": p.metadata.num_row_groups,
            }
        except Exception:
            time.sleep(0.3)

    return {
        "output_file": output_file,
        "status": "Saved successfully",
    }