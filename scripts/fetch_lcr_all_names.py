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
DEBUG_LOGIN_PATH = Path("data/debug_login_page.html")
DEBUG_TEXT_PATH = Path("data/debug_member_list_text.txt")
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


def wait_for_input(driver: webdriver.Chrome, css_selector: str):
    return WebDriverWait(driver, LONG_WAIT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
    )


def login(driver: webdriver.Chrome) -> None:
    if not USERNAME or not PASSWORD:
        raise RuntimeError("Missing LCR_USERNAME and/or LCR_PASSWORD.")

    log("Opening LCR login page")
    driver.get(LCR_BASE)
    log(f"Current URL after opening login page: {driver.current_url}")

    DEBUG_LOGIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEBUG_LOGIN_PATH.write_text(driver.page_source, encoding="utf-8")

    user_input = wait_for_input(
        driver,
        "input#username-input, input[name='username'], input[type='email'], input[type='text']",
    )
    user_input.clear()
    user_input.send_keys(USERNAME)
    user_input.send_keys(Keys.ENTER)

    pwd_input = wait_for_input(
        driver,
        "input#password-input, input[name='password'], input[type='password']",
    )
    pwd_input.clear()
    pwd_input.send_keys(PASSWORD)
    pwd_input.send_keys(Keys.ENTER)

    WebDriverWait(driver, LONG_WAIT).until(
        lambda d: "churchofjesuschrist.org" in d.current_url
    )
    log(f"Login submitted successfully. Current URL: {driver.current_url}")


def get_body_text(driver: webdriver.Chrome) -> str:
    return driver.find_element(By.TAG_NAME, "body").text


def extract_all_names_from_rendered_text(body_text: str) -> list[str]:
    names: set[str] = set()

    for line in body_text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("\t")]
        possible_name = parts[0] if parts else ""

        if not possible_name:
            continue

        if "," not in possible_name:
            continue

        if len(possible_name) > 80:
            continue

        if re.search(
            r"\d|@|NameCount|Phone|E-mail|Email|Birth Date|Gender|Age|Show|Search",
            possible_name,
            re.I,
        ):
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

        WebDriverWait(driver, LONG_WAIT).until(
            lambda d: "NameCount:" in get_body_text(d)
        )

        body_text = get_body_text(driver)
        DEBUG_TEXT_PATH.write_text(body_text, encoding="utf-8")
        log(f"Wrote debug rendered text to {DEBUG_TEXT_PATH}")

        names = extract_all_names_from_rendered_text(body_text)

        if len(names) < 50:
            raise RuntimeError(
                f"Only found {len(names)} names. Member list may not have fully loaded."
            )

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
