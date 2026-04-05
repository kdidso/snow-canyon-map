from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LCR_BASE = "https://lcr.churchofjesuschrist.org"
MEMBER_LIST_PAGE_URL = f"{LCR_BASE}/records/member-list?lang=eng"
UNIT_NUMBER = os.getenv("UNIT_NUMBER", "253022").strip()

USERNAME = os.getenv("LCR_USERNAME", "").strip()
PASSWORD = os.getenv("LCR_PASSWORD", "").strip()

OUTPUT_PATH = Path("data/All_Names.txt")
LONG_WAIT = 60


def log(msg: str) -> None:
    print(f"[INFO] {msg}")


def err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


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


def build_requests_session_from_driver(driver: webdriver.Chrome) -> requests.Session:
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )

    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": MEMBER_LIST_PAGE_URL,
        }
    )
    return session


def member_list_api_url(unit_number: str) -> str:
    return f"{LCR_BASE}/api/umlu/report/member-list?lang=eng&unitNumber={unit_number}"


def fetch_json(session: requests.Session, url: str):
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def extract_all_names(payload: list[dict]) -> list[str]:
    results = []

    for person in payload:
        preferred = (person.get("directoryPreferredLocal") or "").strip()
        if preferred:
            results.append(preferred)
            continue

        # fallback if needed
        name = (
            person.get("nameListPreferredLocal")
            or (person.get("nameFormats") or {}).get("listPreferredLocal")
            or ""
        ).strip()
        if name:
            results.append(name)

    return results


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    driver = make_driver()
    try:
        login(driver)
        driver.get(MEMBER_LIST_PAGE_URL)

        session = build_requests_session_from_driver(driver)
        url = member_list_api_url(UNIT_NUMBER)
        log(f"Fetching member roster: {url}")
        payload = fetch_json(session, url)

        if not isinstance(payload, list):
            raise RuntimeError("Member-list API did not return a list.")

        names = extract_all_names(payload)
        if not names:
            raise RuntimeError("No names found in member-list payload.")

        names = sorted(set(n.strip() for n in names if n.strip()), key=str.casefold)
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
