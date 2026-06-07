from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LCR_BASE = "https://lcr.churchofjesuschrist.org"
MEMBER_LIST_PAGE_URL = f"{LCR_BASE}/mlt/records/member-list?lang=eng"

USERNAME = os.getenv("LCR_USERNAME", "").strip()
PASSWORD = os.getenv("LCR_PASSWORD", "").strip()

OUTPUT_PATH = Path("data/All_Names.txt")
DEBUG_HTML_PATH = Path("data/debug_member_list_page.html")
DEBUG_TEXT_PATH = Path("data/debug_member_list_text.txt")
DEBUG_CANDIDATES_PATH = Path("data/debug_member_name_candidates.txt")

LONG_WAIT = 60
ROSTER_WAIT = 180

NAME_RE = re.compile(r"^[A-Za-zÀ-ÿ0-9'’.\- ]+,\s+[A-Za-zÀ-ÿ0-9'’.\- ]+$")
ROW_RE = re.compile(
    r"^(?P<name>[A-Za-zÀ-ÿ0-9'’.\- ]+,\s+[A-Za-zÀ-ÿ0-9'’.\- ]+)\s+"
    r"(?P<gender>M|F)\s+"
    r"(?P<age>\d{1,3})\s+"
    r"(?P<birth>\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b"
)


def log(msg: str) -> None:
    print(f"[INFO] {msg}")


def make_driver() -> webdriver.Chrome:
    opts = ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1600,2200")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-US")
    return webdriver.Chrome(options=opts)


def login(driver: webdriver.Chrome) -> None:
    if not USERNAME or not PASSWORD:
        raise RuntimeError("Missing LCR_USERNAME and/or LCR_PASSWORD.")

    log("Opening LCR login page")
    driver.get(LCR_BASE)

    user_input = WebDriverWait(driver, LONG_WAIT).until(
        EC.presence_of_element_located((By.ID, "username-input"))
    )
    user_input.clear()
    user_input.send_keys(USERNAME)
    user_input.send_keys(Keys.ENTER)

    pwd_input = WebDriverWait(driver, LONG_WAIT).until(
        EC.presence_of_element_located((By.ID, "password-input"))
    )
    pwd_input.clear()
    pwd_input.send_keys(PASSWORD)
    pwd_input.send_keys(Keys.ENTER)

    WebDriverWait(driver, LONG_WAIT).until(EC.url_contains(LCR_BASE))
    log("Login submitted successfully")


def get_body_text(driver: webdriver.Chrome) -> str:
    return driver.find_element(By.TAG_NAME, "body").text


def normalize_status_lines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n\s*(Out-of-Unit|Not Baptized)\s*\n", "\n", text)
    return text


def valid_name(name: str) -> bool:
    name = name.strip()

    if name == "Come, Follow Me":
        return False

    if len(name) > 90:
        return False

    if "," not in name:
        return False

    return bool(NAME_RE.match(name))


def extract_all_names_from_rendered_text(body_text: str) -> list[str]:
    text = normalize_status_lines(body_text)
    names: set[str] = set()
    debug_candidates: list[str] = []

    # Method 1: parse normal rendered rows, whether separated by tabs or spaces.
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line_for_match = re.sub(r"\s+", " ", line.replace("\t", " ")).strip()
        match = ROW_RE.match(line_for_match)

        if match:
            name = match.group("name").strip()
            debug_candidates.append(f"ROW MATCH: {line_for_match}")
            if valid_name(name):
                names.add(name)

    # Method 2: parse multi-line rows.
    # Example:
    #   Freeman, Tyler
    #   M
    #   25
    #   18 Mar 2001
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for i, line in enumerate(lines):
        if not valid_name(line):
            continue

        # Look ahead a few lines to find M/F, age, and birth date.
        lookahead = " ".join(lines[i : i + 8])
        lookahead = re.sub(r"\s+", " ", lookahead).strip()

        match = ROW_RE.match(lookahead)
        if match:
            name = match.group("name").strip()
            debug_candidates.append(f"MULTILINE MATCH: {lookahead}")
            if valid_name(name):
                names.add(name)

    DEBUG_CANDIDATES_PATH.write_text(
        "\n".join(debug_candidates),
        encoding="utf-8",
    )

    return sorted(names, key=str.casefold)


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    driver = make_driver()
    try:
        login(driver)

        log(f"Loading member list page: {MEMBER_LIST_PAGE_URL}")
        driver.get(MEMBER_LIST_PAGE_URL)

        log("Waiting for rendered roster text")
        WebDriverWait(driver, ROSTER_WAIT).until(
            lambda d: (
                "Name" in get_body_text(d)
                and "Gender" in get_body_text(d)
                and "Birth Date" in get_body_text(d)
                and get_body_text(d).count(",") > 50
            )
        )

        DEBUG_HTML_PATH.write_text(driver.page_source, encoding="utf-8")
        log(f"Wrote debug page source to {DEBUG_HTML_PATH}")

        body_text = get_body_text(driver)
        DEBUG_TEXT_PATH.write_text(body_text, encoding="utf-8")
        log(f"Wrote debug rendered text to {DEBUG_TEXT_PATH}")

        names = extract_all_names_from_rendered_text(body_text)
        log(f"Wrote debug candidates to {DEBUG_CANDIDATES_PATH}")

        if len(names) < 50:
            raise RuntimeError(
                f"Only found {len(names)} names. Member list may not have fully loaded."
            )

        if "Come, Follow Me" in names:
            raise RuntimeError("Bad non-member entry detected: Come, Follow Me")

        OUTPUT_PATH.write_text("\n".join(names), encoding="utf-8")
        log(f"Wrote {len(names)} names to {OUTPUT_PATH}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
