from pathlib import Path
import re
import unicodedata

BASE = Path("data")
ALL_NAMES_FILE = BASE / "All_Names.txt"
EXTRACTED_NAMES_FILE = BASE / "Name_Extraction.txt"
NEW_NAMES_FILE = BASE / "New_Names.txt"
NAMES_TO_DELETE_FILE = BASE / "Names_to_Delete.txt"
IGNORE_NEW_FILE = BASE / "ignore_new_names.txt"


def normalize_name(name: str) -> str:
    """
    Normalize names for comparison:
    - lowercase
    - remove accents
    - normalize apostrophes
    - collapse punctuation/spaces
    """
    if not name:
        return ""

    name = name.strip()

    # Normalize unicode and remove accents
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))

    # Normalize apostrophes/quotes
    name = name.replace("’", "'").replace("`", "'")

    # Remove spaces right after apostrophes: O' Brien -> O'Brien
    name = re.sub(r"'\s+", "'", name)

    # Collapse repeated whitespace
    name = re.sub(r"\s+", " ", name).strip()

    return name.lower()


def read_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_names(path: Path, names: list[str]) -> None:
    path.write_text("\n".join(sorted(names, key=str.casefold)), encoding="utf-8")


def build_normalized_map(names: list[str]) -> dict[str, str]:
    """
    Returns normalized_name -> original_name
    First occurrence wins.
    """
    result = {}
    for name in names:
        norm = normalize_name(name)
        if norm and norm not in result:
            result[norm] = name
    return result


def main() -> None:
    all_names_raw = read_names(ALL_NAMES_FILE)
    extracted_names_raw = read_names(EXTRACTED_NAMES_FILE)
    ignore_new_raw = read_names(IGNORE_NEW_FILE)

    all_names_map = build_normalized_map(all_names_raw)
    extracted_names_map = build_normalized_map(extracted_names_raw)
    ignore_new_set = {normalize_name(name) for name in ignore_new_raw}

    all_names_norm = set(all_names_map.keys())
    extracted_names_norm = set(extracted_names_map.keys())

    # Names in roster but not in geojson, excluding ignored names
    new_names_norm = (all_names_norm - extracted_names_norm) - ignore_new_set

    # Names in geojson but not in roster
    names_to_delete_norm = extracted_names_norm - all_names_norm

    # Convert back to original display forms
    new_names = [all_names_map[n] for n in new_names_norm]
    names_to_delete = [extracted_names_map[n] for n in names_to_delete_norm]

    write_names(NEW_NAMES_FILE, new_names)
    write_names(NAMES_TO_DELETE_FILE, names_to_delete)

    print(f"New names (after ignore + normalization): {len(new_names)}")
    print(f"Names to delete: {len(names_to_delete)}")


if __name__ == "__main__":
    main()
