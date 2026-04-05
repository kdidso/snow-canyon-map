import re
from pathlib import Path

BASE = Path("data")
DELETE_FILE = BASE / "Names_to_Delete.txt"
SEARCH_BAR_FILE = BASE / "search_bar_code.txt"


def read_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def main() -> None:
    names_to_delete = read_names(DELETE_FILE)
    content = SEARCH_BAR_FILE.read_text(encoding="utf-8")

    removed = []

    pattern = re.compile(
        r'\{\s*name:\s*"(?P<name>[^"]+)"\s*,\s*image:\s*"[^"]*"\s*,\s*url:\s*"[^"]+"\s*\},?',
        re.DOTALL
    )

    def replacer(match: re.Match) -> str:
        name = match.group("name").strip()
        if name in names_to_delete:
            removed.append(name)
            return ""
        return match.group(0)

    updated = pattern.sub(replacer, content)

    SEARCH_BAR_FILE.write_text(updated, encoding="utf-8")

    print(f"Removed {len(removed)} people from search bar code.")


if __name__ == "__main__":
    main()
