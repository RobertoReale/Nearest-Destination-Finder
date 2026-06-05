import pandas as pd

def import_addresses_from_csv(file_path):
    """Import a list of addresses from a CSV file.
    Looks for a column named 'address', 'destination', 'indirizzo', or 'destinazione'.
    Falls back to the first column if none is found.
    """
    try:
        df = pd.read_csv(file_path)
        columns_lower = [col.lower() for col in df.columns]

        target_col = None
        for col_name in ['address', 'destination', 'indirizzo', 'destinazione']:
            if col_name in columns_lower:
                target_col = df.columns[columns_lower.index(col_name)]
                break

        if target_col is None:
            if len(df.columns) > 0:
                target_col = df.columns[0]
            else:
                return []

        addresses = df[target_col].dropna().astype(str).tolist()
        return [addr.strip() for addr in addresses if addr.strip()]

    except Exception as e:
        print(f"Error importing CSV: {e}")
        return []
