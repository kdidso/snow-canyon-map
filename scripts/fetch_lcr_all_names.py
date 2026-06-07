from __future__ import annotations

import html
import json
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
LONG_WAIT = 60


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


def decode_page_source(page_source: str) -> str:
    """
    The new LCR member-list page appears to store roster data inside escaped
    JSON/text in the page source. Decode common HTML/JSON escaping so regex can
    find listPreferredLocal values.
    """
    text = html.unescape(page_source)

    # Some embedded data appears as escaped JSON, e.g. \"listPreferredLocal\".
    text = text.replace('\\"', '"')
    text = text.replace("\\u0022", '"')
    text = text.replace("\\u0026", "&")
    text = text.replace("\\/", "/")

    return text


def extract_all_names_from_page(page_source: str) -> list[str]:
    text = decode_page_source(page_source)

    names: set[str] = set()

    # Primary field seen in the new page source.
    for match in re.finditer(r'"listPreferredLocal"\s*:\s*"([^"]+)"', text):
        name = match.group(1).strip()
        if name:
            names.add(name)

    # Fallbacks, in case LCR varies the field names.
    for field in (
        "directoryPreferredLocal",
        "nameListPreferredLocal",
        "householdDirectoryNameLocal",
        "displayName",
    ):
        pattern = rf'"{re.escape(field)}"\s*:\s*"([^"]+)"'
        for match in re.finditer(pattern, text):
            name = match.group(1).strip()
            if name:
                names.add(name)

    return sorted(names, key=str.casefold)


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    driver = make_driver()
    try:
        login(driver)

        log(f"Loading member list page: {MEMBER_LIST_PAGE_URL}")
        driver.get(MEMBER_LIST_PAGE_URL)

        WebDriverWait(driver, LONG_WAIT).until(
            lambda d: "listPreferredLocal" in decode_page_source(d.page_source)
            or "householdMembers" in decode_page_source(d.page_source)
            or "displayName" in decode_page_source(d.page_source)
        )

        page_source = driver.page_source

        # Helpful while this new LCR page format is being tested.
        DEBUG_HTML_PATH.write_text(page_source, encoding="utf-8")
        log(f"Wrote debug page source to {DEBUG_HTML_PATH}")

        names = extract_all_names_from_page(page_source)

        if not names:
            raise RuntimeError("No names found in member-list page source.")

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
