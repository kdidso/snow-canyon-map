from pathlib import Path

BASE = Path("data")
NEW_NAMES_FILE = BASE / "New_Names.txt"
IGNORE_FILE = BASE / "ignore_new_names.txt"


def read_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def write_names(path: Path, names: set[str]) -> None:
    path.write_text("\n".join(sorted(names, key=str.casefold)), encoding="utf-8")


def main() -> None:
    new_names = read_names(NEW_NAMES_FILE)
    ignore_names = read_names(IGNORE_FILE)

    filtered = new_names - ignore_names
    write_names(NEW_NAMES_FILE, filtered)

    print(f"Filtered New_Names.txt. Remaining: {len(filtered)}")


if __name__ == "__main__":
    main()
