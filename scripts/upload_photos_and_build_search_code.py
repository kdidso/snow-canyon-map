import os
import re
from pathlib import Path

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


def build_entry_line(name: str, file_id: str) -> str:
    image_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"
    page_url = f"{SITE_BASE_URL}/{slugify(name)}"

    return (
        '  { name: "'
        + js_escape(name)
        + '", image: "'
        + js_escape(image_url)
        + '", url: "'
        + js_escape(page_url)
        + '" }'
    )


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


# -----------------------------
# MAIN
# -----------------------------
def main():
    ensure_directories()

    files_to_upload = sorted(
        [
            p
            for p in DOWNLOADS_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
        ]
    )

    existing_people = read_existing_people(OUTPUT_FILE)
    existing_names = {p["name"] for p in existing_people}

    if not files_to_upload:
        print("No image files found in data/downloaded_photos. Nothing to do.")
        print(f"Existing people count: {len(existing_people)}")
        return

    drive_service = authenticate_drive()

    uploaded_count = 0
    skipped_count = 0

    for file_path in files_to_upload:
        display_name = filename_to_display_name(file_path.name)

        if not display_name:
            print(f"Skipping blank name from file: {file_path.name}")
            skipped_count += 1
            continue

        if display_name in existing_names:
            print(f"Skipping duplicate (already exists): {display_name}")
            delete_local_file(file_path)
            skipped_count += 1
            continue

        print(f"Uploading {file_path.name} ...")
        file_id = upload_file_to_drive(drive_service, file_path, DRIVE_FOLDER_ID)

        existing_people.append({
            "name": display_name,
            "image": f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000",
            "url": f"{SITE_BASE_URL}/{slugify(display_name)}"
        })
        existing_names.add(display_name)
        uploaded_count += 1

        print(f"Uploaded: {display_name} -> {file_id}")
        delete_local_file(file_path)

    existing_people.sort(key=lambda p: p["name"].lower())
    write_people_js(existing_people, OUTPUT_FILE)

    print("")
    print("Done.")
    print(f"Uploaded new entries: {uploaded_count}")
    print(f"Skipped entries: {skipped_count}")
    print(f"Updated file: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
