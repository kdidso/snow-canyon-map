from pathlib import Path


BASE = Path("data")
ALL_NAMES_FILE = BASE / "All_Names.txt"
EXTRACTED_NAMES_FILE = BASE / "Name_Extraction.txt"
NEW_NAMES_FILE = BASE / "New_Names.txt"
NAMES_TO_DELETE_FILE = BASE / "Names_to_Delete.txt"


def read_names(file_path: Path) -> set[str]:
    if not file_path.exists():
        return set()
    return {line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()}


def write_names(file_path: Path, names: set[str]) -> None:
    file_path.write_text("\n".join(sorted(names, key=str.casefold)), encoding="utf-8")


def main() -> None:
    all_names = read_names(ALL_NAMES_FILE)
    extracted_names = read_names(EXTRACTED_NAMES_FILE)

    new_names = all_names - extracted_names
    names_to_delete = extracted_names - all_names

    write_names(NEW_NAMES_FILE, new_names)
    write_names(NAMES_TO_DELETE_FILE, names_to_delete)

    print("Comparison complete.")
    print(f"New names: {len(new_names)}")
    print(f"Names to delete: {len(names_to_delete)}")


if __name__ == "__main__":
    main()
