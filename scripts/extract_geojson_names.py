import json
from pathlib import Path

INPUT_PATH = Path("member_locations_JSO.geojson")
OUTPUT_PATH = Path("data/Name_Extraction.txt")


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_PATH}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    features = data.get("features", [])

    names = []
    for feat in features:
        props = feat.get("properties", {})
        last_name = (props.get("Last_Name") or "").strip()
        first_name = (props.get("First_Name") or "").strip()

        formatted = f"{last_name}, {first_name}".strip(", ").strip()
        if formatted:
            names.append(formatted)

    names = sorted(set(names), key=str.casefold)
    OUTPUT_PATH.write_text("\n".join(names), encoding="utf-8")
    print(f"Wrote {len(names)} extracted names to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
