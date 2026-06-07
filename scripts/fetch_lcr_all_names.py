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

LONG_WAIT = 60
ROSTER_WAIT = 180


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


def clean_name_status_lines(text: str) -> str:
    """
    LCR sometimes renders rows like:
      Freeman, Tyler
      Out-of-Unit
          M 25 18 Mar 2001 ...

    Convert that to:
      Freeman, Tyler    M 25 18 Mar 2001 ...
    so it can be parsed the same way as normal rows.
    """
    text = re.sub(r"\n(?:Out-of-Unit|Not Baptized)\n\s*\t", "\t", text)
    return text


def extract_all_names_from_rendered_text(body_text: str) -> list[str]:
    names: set[str] = set()

    text = clean_name_status_lines(body_text)

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("\t")]

        # Expected member row:
        # Name | Gender | Age | Birth Date | Phone Number | E-mail
        if len(parts) < 4:
            continue

        possible_name = parts[0]
        gender = parts[1]
        age = parts[2]
        birth_date = parts[3]

        if gender not in {"M", "F"}:
            continue

        if not age.isdigit():
            continue

        if "," not in possible_name:
            continue

        if len(possible_name) > 90:
            continue

        if not re.match(r"^[A-Za-zÀ-ÿ'’.\- ]+,\s+[A-Za-zÀ-ÿ'’.\- ]+", possible_name):
            continue

        if not re.search(r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b", birth_date):
            continue

        names.add(possible_name)

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
