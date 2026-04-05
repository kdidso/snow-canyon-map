from pathlib import Path

BASE = Path("data")
DELETE_FILE = BASE / "Names_to_Delete.txt"
IGNORE_FILE = BASE / "ignore_delete_names.txt"


def read_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def write_names(path: Path, names: set[str]) -> None:
    path.write_text("\n".join(sorted(names, key=str.casefold)), encoding="utf-8")


def main() -> None:
    delete_names = read_names(DELETE_FILE)
    ignore_names = read_names(IGNORE_FILE)

    filtered = delete_names - ignore_names
    write_names(DELETE_FILE, filtered)

    print(f"Filtered Names_to_Delete.txt. Remaining: {len(filtered)}")


if __name__ == "__main__":
    main()
