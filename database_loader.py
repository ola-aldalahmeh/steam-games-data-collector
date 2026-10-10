import os
import mysql.connector
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SQL = """
INSERT INTO steam_games
    (App_ID, Game_Name, Released_Date, `Release_Year`, `Release_Month`,
     `Price_USD`, `Is_Free`, Discount, Recent_Reviews, Recent_Reviews_Score,
     All_Reviews, All_Reviews_Score, Review_Trajectory, Developer, Publisher, Link)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    Game_Name=VALUES(Game_Name),
    Released_Date=VALUES(Released_Date),
    `Release_Year`=VALUES(`Release_Year`),
    `Release_Month`=VALUES(`Release_Month`),
    `Price_USD`=VALUES(`Price_USD`),
    `Is_Free`=VALUES(`Is_Free`),
    Discount=VALUES(Discount),
    Recent_Reviews=VALUES(Recent_Reviews),
    Recent_Reviews_Score=VALUES(Recent_Reviews_Score),
    All_Reviews=VALUES(All_Reviews),
    All_Reviews_Score=VALUES(All_Reviews_Score),
    Review_Trajectory=VALUES(Review_Trajectory),
    Developer=VALUES(Developer),
    Publisher=VALUES(Publisher),
    Link=VALUES(Link)
"""

COLUMNS = [
    "App ID", "Game Name", "Release Date", "Release Year", "Release Month",
    "Price (USD)", "Is Free", "Discount (%)", "Recent Reviews",
    "Recent Reviews Score", "All Reviews", "All Reviews Score",
    "Review Trajectory", "Developer", "Publisher", "Link",
]


def load_to_db(csv_path: Path = Path("steam_games.csv")) -> int:
    df = pd.read_csv(csv_path)

    df["Release Date"] = pd.to_datetime(
        df["Release Date"], format="mixed", errors="coerce"
    ).dt.strftime("%Y-%m-%d")


    df = df[COLUMNS].astype(object).where(df[COLUMNS].notna(), None)
    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]

    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "steam_games_data"),
    )

    try:
        cursor = connection.cursor()
        try:
            cursor.execute("ALTER TABLE steam_games ADD UNIQUE KEY (App_ID)")
            connection.commit()
            print("Unique key added.")
        except mysql.connector.Error as e:
            if e.errno == 1061:
                print("Unique key already exists, skipping.")
            else:
                raise

        cursor.executemany(SQL, rows)
        connection.commit()
        print(f"{cursor.rowcount} rows affected.")
        cursor.close()
        return len(rows)
    finally:
        connection.close()


if __name__ == "__main__":
    load_to_db()