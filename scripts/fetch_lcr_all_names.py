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

TARGET_UNIT_NAME = "Snow Canyon YSA Ward (26-35)"
TARGET_UNIT_ID = "253022"
TARGET_ORGANIZATION_NAME = "All Members"
TARGET_ORGANIZATION_VALUE = "ALL"

USERNAME = os.getenv("LCR_USERNAME", "").strip()
PASSWORD = os.getenv("LCR_PASSWORD", "").strip()

OUTPUT_PATH = Path("data/All_Names.txt")
DEBUG_HTML_PATH = Path("data/debug_member_list_page.html")
DEBUG_TEXT_PATH = Path("data/debug_member_list_text.txt")
DEBUG_ROWS_PATH = Path("data/debug_member_list_rows.txt")
DEBUG_SCREENSHOT_PATH = Path("data/debug_member_list_page.png")
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
    WebDriverWait(driver, LONG_WAIT).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    log("Login submitted successfully")


def select_ward_and_organization(driver: webdriver.Chrome) -> None:
    """Select the target ward and the full-roster organization filter."""
    wait = WebDriverWait(driver, LONG_WAIT)

    def select_containing_value(d: webdriver.Chrome, wanted_value: str):
        for element in d.find_elements(By.TAG_NAME, "select"):
            options = element.find_elements(By.TAG_NAME, "option")
            if any(option.get_attribute("value") == wanted_value for option in options):
                return element
        return False

    def set_hidden_select(element, value: str) -> None:
        # LCR visually replaces its native select controls, leaving the real
        # <select> hidden. A normal Selenium Select click therefore fails.
        driver.execute_script(
            """
            const select = arguments[0];
            const value = arguments[1];
            select.value = value;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            """,
            element,
            value,
        )

    unit_element = wait.until(
        lambda d: select_containing_value(d, TARGET_UNIT_ID)
    )
    log(f"Selecting unit: {TARGET_UNIT_NAME} ({TARGET_UNIT_ID})")
    set_hidden_select(unit_element, TARGET_UNIT_ID)

    # Confirm LCR accepted the unit change. The control may be replaced during
    # the rerender, so this deliberately finds it again on every poll.
    WebDriverWait(driver, ROSTER_WAIT).until(
        lambda d: (
            (element := select_containing_value(d, TARGET_UNIT_ID))
            and element.get_attribute("value") == TARGET_UNIT_ID
        )
    )

    # The organization control appears after the unit rerender. Its stable
    # full-roster value is ALL (displayed as "All Members").
    organization_element = WebDriverWait(driver, ROSTER_WAIT).until(
        lambda d: select_containing_value(d, TARGET_ORGANIZATION_VALUE)
    )
    log(
        f"Selecting organization: {TARGET_ORGANIZATION_NAME} "
        f"({TARGET_ORGANIZATION_VALUE})"
    )
    set_hidden_select(organization_element, TARGET_ORGANIZATION_VALUE)

    WebDriverWait(driver, LONG_WAIT).until(
        lambda d: (
            (element := select_containing_value(d, TARGET_ORGANIZATION_VALUE))
            and element.get_attribute("value") == TARGET_ORGANIZATION_VALUE
        )
    )


def get_body_text(driver: webdriver.Chrome) -> str:
    return driver.find_element(By.TAG_NAME, "body").text


def clean_name(name: str) -> str:
    # Removes status labels that may appear inside the name cell.
    name = re.sub(r"\s*(Out-of-Unit|Not Baptized)\s*", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def looks_like_name(name: str) -> bool:
    if not name:
        return False

    if name == "Come, Follow Me":
        return False

    if len(name) > 90:
        return False

    return bool(
        re.match(
            r"^[A-Za-zÀ-ÿ'’.\- ]+,\s+[A-Za-zÀ-ÿ'’.\- ]+$",
            name,
        )
    )


def extract_all_names_from_table_cells(driver: webdriver.Chrome) -> list[str]:
    names: set[str] = set()
    debug_rows: list[str] = []

    rows = driver.find_elements(By.CSS_SELECTOR, "tr")

    for row in rows:
        cells = row.find_elements(By.CSS_SELECTOR, "td")
        cell_texts = [cell.text.strip() for cell in cells]

        if cell_texts:
            debug_rows.append(" | ".join(cell_texts))

        # Expected:
        # checkbox | name | gender | age | birth date | phone | email
        if len(cell_texts) < 5:
            continue

        possible_name = clean_name(cell_texts[1])
        gender = cell_texts[2].strip()
        age = cell_texts[3].strip()
        birth_date = cell_texts[4].strip()

        if gender not in {"M", "F"}:
            continue

        if not age.isdigit():
            continue

        if not re.search(r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b", birth_date):
            continue

        if not looks_like_name(possible_name):
            continue

        names.add(possible_name)

    DEBUG_ROWS_PATH.write_text("\n".join(debug_rows), encoding="utf-8")
    return sorted(names, key=str.casefold)


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    driver = make_driver()
    try:
        login(driver)

        log(f"Loading member list page: {MEMBER_LIST_PAGE_URL}")
        driver.get(MEMBER_LIST_PAGE_URL)
        select_ward_and_organization(driver)

        log("Waiting for rendered roster text")
        WebDriverWait(driver, ROSTER_WAIT).until(
            lambda d: "Abarca," in get_body_text(d)
            or (
                "Name" in get_body_text(d)
                and "Gender" in get_body_text(d)
                and "Birth Date" in get_body_text(d)
                and get_body_text(d).count(",") > 50
            )
        )

        page_source = driver.page_source
        DEBUG_HTML_PATH.write_text(page_source, encoding="utf-8")
        log(f"Wrote debug page source to {DEBUG_HTML_PATH}")

        body_text = get_body_text(driver)
        DEBUG_TEXT_PATH.write_text(body_text, encoding="utf-8")
        log(f"Wrote debug rendered text to {DEBUG_TEXT_PATH}")

        names = extract_all_names_from_table_cells(driver)
        log(f"Wrote debug rows to {DEBUG_ROWS_PATH}")

        if len(names) < 50:
            raise RuntimeError(
                f"Only found {len(names)} names. Member list may not have fully loaded."
            )

        if "Come, Follow Me" in names:
            raise RuntimeError("Bad non-member entry detected: Come, Follow Me")

        OUTPUT_PATH.write_text("\n".join(names), encoding="utf-8")
        log(f"Wrote {len(names)} names to {OUTPUT_PATH}")

    except Exception:
        # Preserve the rendered failure state as GitHub Actions artifacts.
        try:
            DEBUG_HTML_PATH.write_text(driver.page_source, encoding="utf-8")
            DEBUG_TEXT_PATH.write_text(get_body_text(driver), encoding="utf-8")
            driver.save_screenshot(str(DEBUG_SCREENSHOT_PATH))
            log(f"Wrote failure screenshot to {DEBUG_SCREENSHOT_PATH}")
        except Exception as debug_error:
            log(f"Could not write all failure diagnostics: {debug_error}")
        raise

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
