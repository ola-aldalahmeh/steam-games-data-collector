import re
import csv
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

log = logging.getLogger(__name__)

BASE_URL = "https://store.steampowered.com/search/?ignore_preferences=1&category1=998&page="
INDEX_CSV = Path("games_index.csv")


def init_browser(headless=True):
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if headless:
        options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)


def extract_app_id(url):
    match = re.search(r"/app/(\d+)", url)
    return match.group(1) if match else None


def load_existing_ids(csv_path: Path):
    if not csv_path.exists():
        return set()
    with csv_path.open(newline="", encoding="utf-8") as f:
        return {row["id"] for row in csv.DictReader(f) if row.get("id")}


def discover_games(max_pages, index_csv=INDEX_CSV, headless=True) -> int:
    existing_ids = load_existing_ids(index_csv)
    log.info(f"Loaded {len(existing_ids)} existing IDs from {index_csv}.")

    browser = init_browser(headless)
    wait = WebDriverWait(browser, 10)
    new_rows = []

    try:
        pbar = tqdm(range(1, max_pages + 1), desc="Discovering games", unit="page")
        for page_num in pbar:
            browser.get(BASE_URL + str(page_num))

            try:
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "a.search_result_row")))
            except Exception:
                log.warning(f"Page {page_num}: timed out, stopping.")
                break

            anchors = browser.find_elements(By.CSS_SELECTOR, "a.search_result_row")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            added = 0

            for anchor in anchors:
                href = anchor.get_attribute("href") or ""
                link = href.split("?")[0].rstrip("/")
                app_id = extract_app_id(link)

                if not app_id or app_id in existing_ids:
                    continue

                existing_ids.add(app_id)
                new_rows.append({
                    "id": app_id,
                    "link": link,
                    "is_scraped": False,
                    "last_updated": "",
                    "discovered": now,
                })
                added += 1

            pbar.set_postfix({"games_found": len(new_rows)})
            log.info(f"Page {page_num}: {added} new games.")
            if page_num < max_pages:
                time.sleep(2)
    finally:
        browser.quit()

    if new_rows:
        df = pd.DataFrame(new_rows)
        write_header = not Path(index_csv).exists()
        df.to_csv(index_csv, mode="a", header=write_header, index=False)
        log.info(f"Wrote {len(df)} new rows to {index_csv}")

    return len(new_rows)