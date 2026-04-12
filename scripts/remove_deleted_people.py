import re
from pathlib import Path

BASE = Path("data")
DELETE_FILE = BASE / "Names_to_Delete.txt"
PEOPLE_FILE = Path("people.js")


def read_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def last_first_to_display(name: str) -> str:
    """
    Convert:
      'Callister, Kasen' -> 'Kasen Callister'
      'Bowden, Christopher & Dakota Rae' -> 'Christopher & Dakota Rae Bowden'
    """
    if "," not in name:
        return name.strip()

    last, first = [part.strip() for part in name.split(",", 1)]
    if not first:
        return last
    return f"{first} {last}".strip()


def parse_people(content: str):
    """
    Extract:
    window.people = [ ... ];
    """
    match = re.search(
        r"^(.*?window\.people\s*=\s*\[\s*)(.*?)(\s*\]\s*;.*)$",
        content,
        flags=re.DOTALL,
    )

    if not match:
        raise ValueError("Could not find window.people array in people.js")

    prefix = match.group(1)
    body = match.group(2)
    suffix = match.group(3)

    entries = re.findall(r"\{.*?\}", body, flags=re.DOTALL)

    return prefix, entries, suffix


def extract_name(entry: str) -> str | None:
    match = re.search(r'name\s*:\s*"([^"]+)"', entry)
    if match:
        return match.group(1).strip()
    return None


def main() -> None:
    raw_names_to_delete = read_names(DELETE_FILE)
    names_to_delete = {last_first_to_display(name) for name in raw_names_to_delete}

    if not PEOPLE_FILE.exists():
        raise FileNotFoundError(f"Missing people.js: {PEOPLE_FILE}")

    content = PEOPLE_FILE.read_text(encoding="utf-8")

    prefix, entries, suffix = parse_people(content)

    kept = []
    removed = []

    for entry in entries:
        name = extract_name(entry)
        if name and name in names_to_delete:
            removed.append(name)
        else:
            kept.append(entry)

    # rebuild clean array (fixes commas automatically)
    if kept:
        new_body = ",\n  ".join(kept)
        updated = f"{prefix}  {new_body}\n{suffix}"
    else:
        updated = f"{prefix}{suffix}"

    PEOPLE_FILE.write_text(updated, encoding="utf-8")

    print(f"Removed {len(removed)} people from people.js")
    if removed:
        print("Removed names:")
        for name in sorted(removed, key=str.casefold):
            print(f"- {name}")


if __name__ == "__main__":
    main()
