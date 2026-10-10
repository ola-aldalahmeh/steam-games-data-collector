import re
import csv
import logging
import time
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from tqdm import tqdm
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException

"""## Config & Logging"""

INDEX_CSV  =Path("games_index.csv")
OUTPUT_CSV = Path("steam_games.csv")

OUTPUT_FIELDS = [
    "App ID", "Game Name",
    "Release Date", "Release Year", "Release Month",
    "Price (USD)", "Is Free", "Discount (%)",
    "Recent Reviews", "Recent Reviews Score",
    "All Reviews",   "All Reviews Score",
    "Review Trajectory",
    "Developer", "Publisher", "Link",
]

REVIEW_SCALE = {
    "overwhelmingly positive": 5,
    "very positive":           4,
    "mostly positive":         3,
    "mixed":                   2,
    "mostly negative":         1,
    "overwhelmingly negative": 0,
    "not available":           np.nan,
}

logging.basicConfig(
    filename="scraper.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

"""## Helper Functions"""

# def init_browser():
#     options = Options()
#     options.add_argument("--no-sandbox")
#     options.add_argument("--disable-dev-shm-usage")
#     options.add_argument("--headless=new")

#     # Don't wait for every image/resource before returning from browser.get()
#     options.page_load_strategy = "eager"

#     # Steam pages contain a lot of images; disabling them saves a lot of bandwidth/time.
#     prefs = {
#         "profile.managed_default_content_settings.images": 2,
#     }
#     options.add_experimental_option("prefs", prefs)

#     options.add_argument(r"--user-data-dir=C:\steam_selenium_profile")
#     options.add_argument("--profile-directory=Default")

#     driver = webdriver.Chrome(options=options)
#     driver.set_page_load_timeout(20)
#     return driver
def init_browser(headless=True, user_data_dir=None):
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if headless:
        options.add_argument("--headless=new")
    options.page_load_strategy = "eager"
    options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument("--profile-directory=Default")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)
    return driver

def safe_text(parent, by, selectors, fallback=None):
    """Try multiple selectors and return the first match."""
    for selector in selectors:
        try:
            text = parent.find_element(by, selector).text.strip()
            if text:
                return text
        except Exception:
            continue
    return fallback

def wait_for(wait, selector):
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        return True
    except Exception:
        return False

# def dismiss_popups(browser, wait):
#     # Age gate
#     try:
#         wait.until(EC.presence_of_element_located((By.ID, "agegate_box")))
#         browser.find_element(By.ID, "ageYear").send_keys("1990")
#         browser.find_element(By.ID, "view_product_page_btn").click()
#         wait.until(EC.staleness_of(browser.find_element(By.ID, "agegate_box")))
#         log.info("Age gate dismissed.")
#     except Exception:
#         pass
#     # Cookie banner
#     try:
#         browser.find_element(By.CSS_SELECTOR, "#cookieAgreementForm button").click()
#         log.info("Cookie banner dismissed.")
#     except Exception:
#         pass

def dismiss_popups(browser, wait):

    try:
        if "agecheck" in browser.current_url:
            wait.until(EC.presence_of_element_located((By.ID, "ageYear")))

            Select(browser.find_element(By.ID, "ageDay")).select_by_value("1")
            Select(browser.find_element(By.ID, "ageMonth")).select_by_visible_text("January")
            Select(browser.find_element(By.ID, "ageYear")).select_by_value("1990")

            browser.find_element(By.ID, "view_product_page_btn").click()

            wait.until(EC.url_contains("/app/"))

            log.info("Age gate dismissed automatically.")

    except Exception as e:
        log.info("No age gate present.")

    try:
        wait.until(EC.presence_of_element_located((By.ID, "cookieAgreementForm")))
        browser.find_element(By.CSS_SELECTOR, "#cookieAgreementForm button").click()
        log.info("Cookie banner dismissed.")
    except Exception:
        pass

def extract_reviews(browser):
    """Extract recent and all-time review summaries from a game's detail page."""
    reviews = browser.find_elements(By.CLASS_NAME, "user_reviews_summary_row")
    if len(reviews) >= 2:
        recent = safe_text(reviews[0], By.CLASS_NAME, ["game_review_summary"])
        all_r  = safe_text(reviews[1], By.CLASS_NAME, ["game_review_summary"])
    elif len(reviews) == 1:
        recent = safe_text(reviews[0], By.CLASS_NAME, ["game_review_summary"])
        all_r  = "Not available"
    else:
        recent = "Not available"
        all_r  = "Not available"
    return recent, all_r

def pass_age_gate(browser):
    if "agecheck" not in browser.current_url:
        return

    try:
        Select(browser.find_element(By.ID, "ageDay")).select_by_value("1")
        Select(browser.find_element(By.ID, "ageMonth")).select_by_value("1")
        Select(browser.find_element(By.ID, "ageYear")).select_by_value("1995")

        browser.find_element(By.ID, "view_product_page_btn").click()

        WebDriverWait(browser, 10).until(
            EC.url_contains("/app/")
        )
    except:
        pass

def extract_price(browser):
    selectors = [
        "div.discount_final_price",   # discounted games
        "div.game_purchase_price",    # normal games
        "div.package_base_price",     # bundles/DLC
        "div.game_purchase_price.price" # free to play
    ]
    for sel in selectors:
        try:
            el = browser.find_element(By.CSS_SELECTOR, sel)
            return el.text.strip()
        except:
            continue
    return "Coming Soon"

def scrape_game_page(browser, wait, link):
    browser.get(link)
    pass_age_gate(browser)
    dismiss_popups(browser, wait)
    wait_for(wait, "div.apphub_AppName")
    wait_for(wait, "#appHubAppName")
    items = {"Link": link}
    items["Game Name"]     = safe_text(browser, By.CSS_SELECTOR, ["div.apphub_AppName"])
    items["Released Date"] = safe_text(browser, By.CSS_SELECTOR, ["div.date"])
    # items["Final Price"]   = safe_text(browser, By.CSS_SELECTOR, ["div.game_purchase_price"])
    items["Final Price"]   = extract_price(browser)
    items["Discount %"]    = safe_text(browser, By.CSS_SELECTOR, ["div.discount_pct"], fallback=None)
    items["Recent Reviews"], items["All Reviews"] = extract_reviews(browser)
    items["Developer"]     = safe_text(browser, By.XPATH, ["//div[@id='developers_list']"])
    items["Publisher"]     = safe_text(browser, By.XPATH, ["//b[text()='Publisher:']/following-sibling::a"])
    return items


def scrape_with_retry(browser, wait, link, retries=2):
    for attempt in range(retries + 1):
        try:
            return scrape_game_page(browser, wait, link)
        except (InvalidSessionIdException, NoSuchWindowException):
            raise  # real crash — let outer loop restart the browser
        except Exception:
            if attempt == retries:
                raise
            time.sleep(0.3)


def load_index(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def save_index(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "link", "is_scraped", "last_updated", "discovered"])
        writer.writeheader()
        writer.writerows(rows)

def parse_price(value):
    if pd.isna(value): return np.nan
    v = str(value).strip().lower()
    if v in ("free", "free to play"): return 0.0
    if v == "not available": return np.nan
    m = re.search(r"[\d]+\.?\d*", v)
    return float(m.group()) if m else np.nan

def parse_discount(value):
    if pd.isna(value): return np.nan
    v = str(value).strip().lower()
    if v in ("no discount", ""): return 0.0
    if v == "not available": return np.nan
    m = re.search(r"\d+", v)
    return float(m.group()) if m else 0.0

def parse_date(value):
    if pd.isna(value): return pd.NaT
    v = str(value).strip()
    if v.lower() == "not available": return pd.NaT
    try: return pd.to_datetime(v, format="%d %b, %Y")
    except ValueError:
        try: return pd.to_datetime(v)
        except: return pd.NaT

def parse_review(value):
    if pd.isna(value): return np.nan
    return REVIEW_SCALE.get(str(value).strip().lower(), np.nan)

def clean_name(value):
    if pd.isna(value): return np.nan
    return re.sub(r"[™®©]", "", str(value)).strip()

def extract_app_id(url):
    if pd.isna(url): return np.nan
    m = re.search(r"/app/(\d+)", str(url))
    return int(m.group(1)) if m else np.nan

def clean_dataframe(df):
    df = df.copy()
    df["Game Name"]   = df["Game Name"].apply(clean_name)
    df["Price (USD)"] = df["Final Price"].apply(parse_price)
    df["Discount (%)"] = df["Discount %"].apply(parse_discount)
    df["Release Date"]  = df["Released Date"].apply(parse_date)
    df["Release Year"]  = df["Release Date"].dt.year
    df["Release Month"] = df["Release Date"].dt.month
    df.drop(columns=["Final Price", "Discount %", "Released Date"], inplace=True)
    df["Recent Reviews Score"] = df["Recent Reviews"].apply(parse_review)
    df["All Reviews Score"]    = df["All Reviews"].apply(parse_review)
    df["Review Trajectory"] = (
        df["Recent Reviews Score"] - df["All Reviews Score"]
    ).apply(lambda x: "Improving" if x > 0 else ("Declining" if x < 0 else ("Stable" if pd.notna(x) else np.nan)))
    df["App ID"]  = df["Link"].apply(extract_app_id)
    df["Is Free"] = df["Price (USD)"] == 0.0
    df = df[[c for c in OUTPUT_FIELDS if c in df.columns]]
    return df

# cleaned_df = clean_dataframe(raw_df)

"""## Scrape Pending Games"""
def save_checkpoint(results_list, output_csv, checkpoint_num):
    if not results_list:
        return
    temp_df = clean_dataframe(pd.DataFrame(results_list))
    if Path(output_csv).exists():
        existing_df = pd.read_csv(output_csv)
        temp_df = pd.concat([existing_df, temp_df], ignore_index=True)
        temp_df.drop_duplicates(subset="App ID", keep="last", inplace=True)
    temp_df.to_csv(output_csv, index=False)
    log.info(f"Checkpoint {checkpoint_num}: Saved {len(temp_df)} rows")


def scrape_pending(index_csv=INDEX_CSV, output_csv=OUTPUT_CSV,
                   headless=True, user_data_dir=None):
    index = load_index(index_csv)
    pending = [r for r in index if r.get("is_scraped", "False").strip() == "False"]
    print(f"{len(pending)} game(s) to scrape.")

    index_by_id = {r["id"]: r for r in index}
    browser = init_browser(headless, user_data_dir)
    wait = WebDriverWait(browser, 5)
    results, ok, err, skipped = [], 0, 0, 0

    try:
        for row in tqdm(pending, desc="Scraping", unit="game"):
            link, app_id = row["link"], row["id"]
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            try:
                raw = scrape_with_retry(browser, wait, link)
                if not raw.get("Game Name"):
                    index_by_id[app_id]["is_scraped"] = "Skipped"
                    index_by_id[app_id]["last_updated"] = now
                    skipped += 1
                    log.info(f"Skipped non-game: {app_id} ({link})")
                    continue
                results.append(raw)
                index_by_id[app_id]["is_scraped"] = "True"
                index_by_id[app_id]["last_updated"] = now
                ok += 1
                log.info(f"Scraped OK: {app_id} — {raw.get('Game Name')}")

                if ok % 25 == 0:
                    save_checkpoint(results, output_csv, ok // 25)
                    results = []
                    save_index(index_csv, list(index_by_id.values()))

                if ok % 300 == 0:
                    browser.quit()
                    browser = init_browser(headless, user_data_dir)
                    wait = WebDriverWait(browser, 5)
            except (InvalidSessionIdException, NoSuchWindowException) as e:
                log.error(f"Browser session died on {app_id}: {e}")
                try:
                    browser.quit()
                except Exception:
                    pass
                browser = init_browser(headless, user_data_dir)
                wait = WebDriverWait(browser, 10)
                pending.append(row)
            except Exception as e:
                err += 1
                log.error(f"Failed: {app_id} ({link}): {e}")
    finally:
        if results:
            save_checkpoint(results, output_csv, "final")
        save_index(index_csv, list(index_by_id.values()))
        browser.quit()

    print(f"\nDone — {ok} scraped, {err} failed. Data saved to {output_csv}")
    return ok, err



