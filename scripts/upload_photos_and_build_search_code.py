import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -----------------------------
# CONFIG
# -----------------------------
DOWNLOADS_DIR = Path("data/downloaded_photos")
OUTPUT_FILE = Path("people.js")
TOKEN_FILE = Path("token.json")

DRIVE_FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]
SCOPES = ["https://www.googleapis.com/auth/drive"]

MAKE_PUBLIC = True
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/jpg"}

SITE_BASE_URL = "https://sites.google.com/view/name-remind"


# -----------------------------
# HELPERS
# -----------------------------
def delete_local_file(file_path: Path):
    try:
        file_path.unlink()
        print(f"Deleted local file: {file_path.name}")
    except Exception as e:
        print(f"Warning: could not delete {file_path.name}: {e}")


def js_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def filename_to_display_name(filename: str) -> str:
    return Path(filename).stem.strip()


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[’']", "", slug)
    slug = re.sub(r'["]', "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def detect_mimetype(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    return "image/jpeg"


def authenticate_drive():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError("OAuth token is invalid and cannot be refreshed.")

    return build("drive", "v3", credentials=creds)


def upload_file_to_drive(service, file_path: Path, folder_id: str) -> str:
    metadata = {
        "name": file_path.name,
        "parents": [folder_id],
    }

    media = MediaFileUpload(
        str(file_path),
        mimetype=detect_mimetype(file_path),
        resumable=False,
    )

    created = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,name",
        )
        .execute()
    )

    file_id = created["id"]

    if MAKE_PUBLIC:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

    return file_id


def read_existing_people(output_file: Path) -> list[dict]:
    if not output_file.exists():
        return []

    text = output_file.read_text(encoding="utf-8")

    pattern = re.compile(
        r'\{\s*name:\s*"([^"]+)",\s*image:\s*"([^"]+)",\s*url:\s*"([^"]+)"\s*\}'
    )

    people = []
    for match in pattern.finditer(text):
        people.append({
            "name": match.group(1).strip(),
            "image": match.group(2).strip(),
            "url": match.group(3).strip(),
        })

    return people


def write_people_js(people: list[dict], output_file: Path):
    lines = ["window.people = ["]
    for i, person in enumerate(people):
        line = (
            '  { name: "'
            + js_escape(person["name"])
            + '", image: "'
            + js_escape(person["image"])
            + '", url: "'
            + js_escape(person["url"])
            + '" }'
        )
        if i < len(people) - 1:
            line += ","
        lines.append(line)
    lines.append("];")
    lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")


def ensure_directories():
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("&", " and ")
    value = re.sub(r"[’']", "", value)
    value = re.sub(r'["]', "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def tokenize_name(value: str) -> list[str]:
    normalized = normalize_text(value)
    if not normalized:
        return []
    tokens = normalized.split()

    # remove very weak tokens
    weak = {"and", "the", "jr", "sr"}
    return [t for t in tokens if t not in weak]


def extract_drive_file_id(image_url: str) -> str | None:
    if not image_url:
        return None

    # Handle thumbnail?id=...
    try:
        parsed = urlparse(image_url)
        qs = parse_qs(parsed.query)
        if "id" in qs and qs["id"]:
            return qs["id"][0]
    except Exception:
        pass

    # Handle /d/<id>/...
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", image_url)
    if m:
        return m.group(1)

    # Handle id=... in raw string
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", image_url)
    if m:
        return m.group(1)

    return None


def build_image_url(file_id: str) -> str:
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"


def list_drive_folder_images(service, folder_id: str) -> list[dict]:
    files = []
    page_token = None

    query = (
        f"'{folder_id}' in parents and trashed = false "
        f"and (mimeType = 'image/jpeg' or mimeType = 'image/png')"
    )

    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, trashed)",
                pageToken=page_token,
                pageSize=1000,
            )
            .execute()
        )

        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return files


def choose_best_duplicate(files: list[dict], current_people_file_id: str | None) -> dict:
    # Prefer the one already referenced in people.js
    if current_people_file_id:
        for f in files:
            if f["id"] == current_people_file_id:
                return f

    # Otherwise keep the newest modified file
    files_sorted = sorted(
        files,
        key=lambda x: (x.get("modifiedTime", ""), x.get("createdTime", ""), x["id"]),
        reverse=True,
    )
    return files_sorted[0]


def trash_drive_file(service, file_id: str):
    service.files().update(fileId=file_id, body={"trashed": True}).execute()


def match_score(person_name: str, drive_name: str) -> tuple[int, int, bool]:
    """
    Returns:
      shared_token_count,
      total_overlap_weight,
      exact_normalized_match
    """
    person_norm = normalize_text(person_name)
    drive_norm = normalize_text(drive_name)

    if person_norm == drive_norm:
        return (999, 999, True)

    person_tokens = tokenize_name(person_name)
    drive_tokens = tokenize_name(drive_name)

    shared = set(person_tokens) & set(drive_tokens)
    shared_count = len(shared)

    # Weighted overlap to slightly reward longer names matching
    weight = sum(len(token) for token in shared)

    return (shared_count, weight, False)


def find_best_matches_for_person(person_name: str, drive_files: list[dict]) -> tuple[list[dict], str]:
    """
    Returns a list of best-matching drive files and a reason string.
    """
    scored = []
    for f in drive_files:
        drive_display_name = filename_to_display_name(f["name"])
        shared_count, weight, exact = match_score(person_name, drive_display_name)
        if exact:
            scored.append((f, 999, 999, True))
        else:
            scored.append((f, shared_count, weight, False))

    exact_matches = [item[0] for item in scored if item[3]]
    if exact_matches:
        return exact_matches, "exact-normalized"

    # Otherwise require at least 2 shared tokens
    scored = [item for item in scored if item[1] >= 2]
    if not scored:
        return [], "no-match"

    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    best_shared = scored[0][1]
    best_weight = scored[0][2]

    best = [item[0] for item in scored if item[1] == best_shared and item[2] == best_weight]
    return best, "token-match"


# -----------------------------
# MAIN
# -----------------------------
def main():
    ensure_directories()
    drive_service = authenticate_drive()

    # -----------------------------
    # STEP 1: Upload local new files
    # -----------------------------
    files_to_upload = sorted(
        [
            p
            for p in DOWNLOADS_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
        ]
    )

    existing_people = read_existing_people(OUTPUT_FILE)
    existing_names = {p["name"] for p in existing_people}

    uploaded_count = 0
    skipped_count = 0
    uploaded_names = []

    if files_to_upload:
        for file_path in files_to_upload:
            display_name = filename_to_display_name(file_path.name)

            if not display_name:
                print(f"Skipping blank name from file: {file_path.name}")
                skipped_count += 1
                continue

            if display_name in existing_names:
                print(f"Skipping duplicate (already exists in people.js): {display_name}")
                delete_local_file(file_path)
                skipped_count += 1
                continue

            print(f"Uploading {file_path.name} ...")
            file_id = upload_file_to_drive(drive_service, file_path, DRIVE_FOLDER_ID)

            existing_people.append({
                "name": display_name,
                "image": build_image_url(file_id),
                "url": f"{SITE_BASE_URL}/{slugify(display_name)}"
            })
            existing_names.add(display_name)
            uploaded_count += 1
            uploaded_names.append(display_name)

            print(f"Uploaded: {display_name} -> {file_id}")
            delete_local_file(file_path)
    else:
        print("No new local image files found in data/downloaded_photos.")

    # -----------------------------
    # STEP 2: Re-read Drive folder and reconcile IDs
    # -----------------------------
    drive_files = list_drive_folder_images(drive_service, DRIVE_FOLDER_ID)

    fixed_ids = []
    duplicates_trashed = []
    ambiguous_people = []
    unmatched_people = []

    for person in existing_people:
        person_name = person["name"]
        current_people_file_id = extract_drive_file_id(person["image"])

        matches, match_reason = find_best_matches_for_person(person_name, drive_files)

        if not matches:
            unmatched_people.append(person_name)
            continue

        if len(matches) == 1:
            chosen = matches[0]
            chosen_id = chosen["id"]

            if current_people_file_id != chosen_id:
                old_id = current_people_file_id
                person["image"] = build_image_url(chosen_id)
                fixed_ids.append({
                    "name": person_name,
                    "old_id": old_id,
                    "new_id": chosen_id,
                    "reason": match_reason,
                })
            continue

        # Multiple matches = duplicates or ambiguous.
        # Only auto-handle if the normalized display names are effectively the same.
        normalized_target = normalize_text(person_name)
        same_name_group = [
            f for f in matches
            if normalize_text(filename_to_display_name(f["name"])) == normalized_target
        ]

        if same_name_group:
            chosen = choose_best_duplicate(same_name_group, current_people_file_id)
            chosen_id = chosen["id"]

            # Trash other same-name duplicates
            for dup in same_name_group:
                if dup["id"] != chosen_id:
                    trash_drive_file(drive_service, dup["id"])
                    duplicates_trashed.append({
                        "name": person_name,
                        "trashed_id": dup["id"],
                        "trashed_file_name": dup["name"],
                        "kept_id": chosen_id,
                        "kept_file_name": chosen["name"],
                    })

            # Update people.js if needed
            if current_people_file_id != chosen_id:
                old_id = current_people_file_id
                person["image"] = build_image_url(chosen_id)
                fixed_ids.append({
                    "name": person_name,
                    "old_id": old_id,
                    "new_id": chosen_id,
                    "reason": "duplicate-resolved",
                })

            continue

        # If multiple candidates remain but not clearly same-name duplicates, don't auto-trash
        ambiguous_people.append({
            "name": person_name,
            "candidate_files": [f'{f["name"]} ({f["id"]})' for f in matches],
        })

    # -----------------------------
    # STEP 3: Sort and write people.js
    # -----------------------------
    existing_people.sort(key=lambda p: p["name"].lower())
    write_people_js(existing_people, OUTPUT_FILE)

    # -----------------------------
    # REPORT
    # -----------------------------
    print("")
    print("Done.")
    print(f"Uploaded new entries: {uploaded_count}")
    print(f"Skipped local duplicates: {skipped_count}")
    print(f"people.js IDs fixed: {len(fixed_ids)}")
    print(f"Duplicate Drive images trashed: {len(duplicates_trashed)}")
    print(f"Unmatched people.js entries: {len(unmatched_people)}")
    print(f"Ambiguous matches not auto-fixed: {len(ambiguous_people)}")
    print(f"Updated file: {OUTPUT_FILE}")

    if uploaded_names:
        print("\nNew uploads:")
        for name in uploaded_names:
            print(f"  - {name}")

    if fixed_ids:
        print("\npeople.js ID fixes:")
        for item in fixed_ids:
            print(
                f'  - {item["name"]}: {item["old_id"]} -> {item["new_id"]} '
                f'[{item["reason"]}]'
            )

    if duplicates_trashed:
        print("\nDuplicate Drive files trashed:")
        for item in duplicates_trashed:
            print(
                f'  - {item["name"]}: trashed "{item["trashed_file_name"]}" '
                f'({item["trashed_id"]}), kept "{item["kept_file_name"]}" '
                f'({item["kept_id"]})'
            )

    if unmatched_people:
        print("\nUnmatched people.js entries:")
        for name in unmatched_people:
            print(f"  - {name}")

    if ambiguous_people:
        print("\nAmbiguous matches not auto-fixed:")
        for item in ambiguous_people:
            print(f'  - {item["name"]}')
            for candidate in item["candidate_files"]:
                print(f"      * {candidate}")


if __name__ == "__main__":
    main()
