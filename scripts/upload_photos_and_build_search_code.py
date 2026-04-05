# scripts/upload_photos_and_build_search_code.py

import os
import re
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -----------------------------
# CONFIG
# -----------------------------
DOWNLOADS_DIR = Path("data/downloaded_photos")
OUTPUT_FILE = Path("data/search_bar_code.txt")
SERVICE_ACCOUNT_FILE = Path("service_account.json")

DRIVE_FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]
SCOPES = ["https://www.googleapis.com/auth/drive"]

MAKE_PUBLIC = True
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


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
    return value.replace("\\", "\\\\").replace('"', '\\"')


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


def build_entry(name: str, file_id: str) -> str:
    image_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"
    page_url = f"https://sites.google.com/view/name-remind/{slugify(name)}"

    return (
        '{ name: "'
        + js_escape(name)
        + '", image: "'
        + js_escape(image_url)
        + '", url: "'
        + js_escape(page_url)
        + '" },'
    )


def detect_mimetype(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    return "image/jpeg"


def authenticate_drive():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
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


def read_existing_names(output_file: Path) -> set[str]:
    if not output_file.exists():
        return set()

    text = output_file.read_text(encoding="utf-8")
    matches = re.findall(r'name:\s*"([^"]+)"', text)
    return {m.strip() for m in matches if m.strip()}


def ensure_directories():
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not OUTPUT_FILE.exists():
        OUTPUT_FILE.write_text("", encoding="utf-8")


def append_entries(entries: list[str], output_file: Path):
    if not entries:
        return

    with output_file.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry + "\n")


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

    if not files_to_upload:
        print("No image files found in data/downloaded_photos. Nothing to do.")
        return

    existing_names = read_existing_names(OUTPUT_FILE)
    drive_service = authenticate_drive()

    new_entries = []
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

    # Optional: delete duplicate local file
    delete_local_file(file_path)

    skipped_count += 1
    continue

        print(f"Uploading {file_path.name} ...")
        file_id = upload_file_to_drive(drive_service, file_path, DRIVE_FOLDER_ID)
        entry = build_entry(display_name, file_id)

        new_entries.append(entry)
        existing_names.add(display_name)
        uploaded_count += 1

        print(f"Uploaded: {display_name} -> {file_id}")

        # ✅ Delete after successful upload
        delete_local_file(file_path)

    append_entries(new_entries, OUTPUT_FILE)

    print("")
    print("Done.")
    print(f"Uploaded new entries: {uploaded_count}")
    print(f"Skipped entries: {skipped_count}")
    print(f"Updated file: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
