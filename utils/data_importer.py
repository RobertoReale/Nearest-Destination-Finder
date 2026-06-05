import pandas as pd

def import_addresses_from_csv(file_path):
    """
    Imports a list of addresses from a CSV file.
    Assumes the addresses are in a column named 'address' or 'indirizzo'.
    If neither exists, it takes the first column.
    """
    try:
        # We try to read the csv file
        df = pd.read_csv(file_path)
        
        # Check for common column names for addresses (case-insensitive)
        columns_lower = [col.lower() for col in df.columns]
        
        target_col = None
        for col_name in ['address', 'indirizzo', 'destinazione', 'destination']:
            if col_name in columns_lower:
                target_col = df.columns[columns_lower.index(col_name)]
                break
        
        # Fallback to the first column if no known name is found
        if target_col is None:
            if len(df.columns) > 0:
                target_col = df.columns[0]
            else:
                return []
                
        # Drop nan values and convert to list of strings
        addresses = df[target_col].dropna().astype(str).tolist()
        return [addr.strip() for addr in addresses if addr.strip()]
        
    except Exception as e:
        print(f"Error importing CSV: {e}")
        return []
