"""
main.py
Entry point for the Steam scraper pipeline.

Stage 1 (crawler.py): discover game links from Steam search pages ->
    games_index.csv
Stage 2 (scraper.py):  visit each pending link's detail page and
    extract data -> steam_games.csv

Stage 3 (database_loader.py): load the scraped CSV into a MySQL database
"""

import argparse
import logging
from pathlib import Path
import scraper      
import database_loader
import crawler
  


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam store scraper pipeline")
    parser.add_argument(
        "--pages", type=int, default=None,
        help="Number of search-result pages to crawl. Prompted for if omitted "
             "(ignored if --skip-crawl is set).",
    )
    parser.add_argument(
        "--index-csv", type=Path, default=Path("games_index.csv"),
        help="Path to the game-link index CSV (default: games_index.csv)",
    )
    parser.add_argument(
        "--output-csv", type=Path, default=Path("steam_games.csv"),
        help="Path to the scraped-data output CSV (default: steam_games.csv)",
    )
    parser.add_argument(
        "--skip-crawl", action="store_true",
        help="Skip discovery and go straight to scraping the existing index.",
    )
    parser.add_argument(
        "--skip-scrape", action="store_true",
        help="Only run the crawler; don't scrape game detail pages.",
    )
    parser.add_argument(
        "--show-browser", action="store_true",
        help="Run Chrome with a visible window instead of headless.",
    )
    parser.add_argument(
        "--user-data-dir", type=str, default=None,
        help="Optional Chrome user-data-dir for the scraper stage "
             "(useful for persisting an age-gate/cookie session).",
    )
    parser.add_argument(
        "--log-file", type=str, default="steam_pipeline.log",
        help="Log file shared by both stages (default: steam_pipeline.log)",
    )
    parser.add_argument(
        "--skip-db", action="store_true",
        help="Don't load the scraped CSV into MySQL.",
    )
    return parser


def setup_logging(log_file: str):
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    args = build_arg_parser().parse_args()
    setup_logging(args.log_file)
    headless = not args.show_browser

    if not args.skip_crawl:
        pages = args.pages
        if pages is None:
            pages = int(input("How many pages do you want to scrape? "))
        found = crawler.discover_games(
            max_pages=pages,
            index_csv=args.index_csv,
            headless=headless,
        )
        print(f"\nCrawler finished. {found} new game(s) added to {args.index_csv}")
    else:
        print("Skipping crawl stage (--skip-crawl).")

    if not args.skip_scrape:
        if not args.index_csv.exists():
            print(f"Index file {args.index_csv} not found — nothing to scrape.")
            return
        scraper.scrape_pending(
            index_csv=args.index_csv,
            output_csv=args.output_csv,
            headless=headless,
            user_data_dir=args.user_data_dir,
        )
    else:
        print("Skipping scrape stage (--skip-scrape).")

    if not args.skip_db:
        if not args.output_csv.exists():
            print(f"{args.output_csv} not found — nothing to load into the DB.")
            return
        n = database_loader.load_to_db(args.output_csv)
        print(f"DB load finished. {n} rows processed.")
    else:
        print("Skipping DB stage (--skip-db).")


if __name__ == "__main__":
    main()
