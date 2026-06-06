import csv


def import_addresses_from_csv(file_path: str) -> list[str]:
    """Import a list of addresses from a CSV file.
    Looks for a column named 'address', 'destination', 'indirizzo', or 'destinazione'.
    Falls back to the first column if none is found.
    Tries utf-8-sig, utf-8, then latin-1 encodings.
    """
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(file_path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames or []
                columns_lower = [c.lower() for c in columns]

                target_col = None
                for col_name in ("address", "destination", "indirizzo", "destinazione"):
                    if col_name in columns_lower:
                        target_col = columns[columns_lower.index(col_name)]
                        break

                if target_col is None and columns:
                    target_col = columns[0]

                if target_col is None:
                    return []

                addresses = []
                for row in reader:
                    val = (row.get(target_col) or "").strip()
                    if val:
                        addresses.append(val)
                return addresses
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"Error importing CSV: {e}")
            return []

    return []


def export_addresses_to_csv(file_path: str, addresses: list[str]) -> bool:
    """Write a list of addresses to a CSV file with an 'address' header."""
    try:
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["address"])
            for addr in addresses:
                writer.writerow([addr])
        return True
    except Exception as e:
        print(f"Error exporting CSV: {e}")
        return False


def export_results_to_csv(file_path: str, results: list[dict], is_tsp: bool,
                           total_distance: str = "", total_duration: str = "") -> bool:
    """Write calculation results to a CSV file."""
    try:
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if is_tsp:
                writer.writerow(["Step", "Destination", "Leg Distance", "Leg Duration"])
                for r in results:
                    writer.writerow([
                        r.get("step", ""),
                        r.get("destination", ""),
                        r.get("distance_text", "N/A"),
                        r.get("duration_text", "N/A"),
                    ])
                if total_distance or total_duration:
                    writer.writerow([])
                    writer.writerow(["Total", "", total_distance, total_duration])
            else:
                writer.writerow(["Rank", "Destination", "Distance", "Duration"])
                rank = 1
                for r in results:
                    if r.get("error"):
                        writer.writerow(["-", r.get("destination", ""), "Error", r.get("error", "")])
                    else:
                        writer.writerow([
                            rank,
                            r.get("destination", ""),
                            r.get("distance_text", "N/A"),
                            r.get("duration_text", "N/A"),
                        ])
                        rank += 1
        return True
    except Exception as e:
        print(f"Error exporting results CSV: {e}")
        return False
