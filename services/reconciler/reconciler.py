import argparse
import os
import re
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from rapidfuzz import fuzz, process, utils
import structlog

logger = structlog.get_logger()

# Minimum fuzzy match score (0-100) to consider an employer name a match
FUZZY_MATCH_THRESHOLD = 85


def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is missing.")
    return psycopg2.connect(db_url)


def fetch_job_listings(conn):
    """Fetches all scraped job listings from the database to use as our matching dictionary."""
    query = "SELECT job_id, employer, location, noc_code FROM job_listings WHERE noc_code IS NOT NULL;"
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    # Structure: { noc_code: [ {job_id, employer, location}, ... ] }
    # Grouping by normalized 5-digit NOC speeds up fuzzy matching significantly.
    listings_by_noc = {}
    for row in rows:
        job_id, employer, location, noc_code = row
        clean_noc = str(noc_code).strip().zfill(5)
        if clean_noc not in listings_by_noc:
            listings_by_noc[clean_noc] = []
        listings_by_noc[clean_noc].append({
            "job_id": job_id,
            "employer": employer.strip(),
            "location": location,
        })
    return listings_by_noc


def process_esdc_data(csv_path: str, conn):
    """Reads the ESDC CSV, matches against Job Bank data, and inserts into esdc_approvals."""
    logger.info("loading_esdc_dataset", path=csv_path)

    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="ISO-8859-1")

    # Normalize CSV column headers to lowercase and strip whitespace
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Standardize varying header formats
    col_map = {
        "employer": "employer_name",
        "employer name": "employer_name",
        "city": "city",
        "province/territory": "province",
        "province": "province",
        "noc": "noc_code",
        "noc code": "noc_code",
        "approved positions": "approved_positions",
        "approved position": "approved_positions",
    }
    df = df.rename(columns={col: col_map.get(col, col) for col in df.columns})

    job_listings_db = fetch_job_listings(conn)
    records_to_insert = []
    match_count = 0

    for _, row in df.iterrows():
        employer = str(row.get("employer_name", "Unknown")).strip()
        city = str(row.get("city", "")).strip()
        province = str(row.get("province", "")).strip()

        # Clean NOC: remove float decimals (e.g., '82030.0') and zero-pad to 5 digits
        raw_noc = str(row.get("noc_code", "")).split(".")[0].strip()
        noc_match = re.search(r"(\d{4,5})", raw_noc)
        noc = noc_match.group(1).zfill(5) if noc_match else ""

        positions = row.get("approved_positions", 1)
        if pd.isna(positions):
            positions = 1

        location_str = f"{city}, {province}".strip(", ")
        matched_job_id = None

        # Cross-reference against Job Bank entries sharing this NOC
        if noc and noc in job_listings_db:
            candidates = job_listings_db[noc]
            employer_names = [c["employer"] for c in candidates]

            best_match = process.extractOne(
                employer,
                employer_names,
                scorer=fuzz.token_sort_ratio,
                processor=utils.default_process,
            )

            if best_match and best_match[1] >= FUZZY_MATCH_THRESHOLD:
                matched_index = best_match[2]
                matched_job_id = candidates[matched_index]["job_id"]
                match_count += 1
                logger.info(
                    "positive_lmia_match_found",
                    esdc_employer=employer,
                    job_bank_employer=best_match[0],
                    score=best_match[1],
                    noc=noc,
                    job_id=matched_job_id,
                )

        records_to_insert.append((
            employer,
            location_str,
            noc,
            int(positions),
            "2026-Q3",
            matched_job_id,
        ))

    logger.info("reconciliation_complete", total_rows=len(df), matched_to_job_bank=match_count)

    query = """
        INSERT INTO esdc_approvals (
            employer_name, location, noc_code, approved_positions, quarter, matched_job_id
        ) VALUES %s;
    """

    with conn.cursor() as cur:
        execute_values(cur, query, records_to_insert)
        conn.commit()

    logger.info("database_insertion_complete", inserted_records=len(records_to_insert))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile ESDC Positive LMIA Data")
    parser.add_argument("csv_file", help="Path to the downloaded ESDC Positive LMIA CSV file")
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        logger.error("file_not_found", path=args.csv_file)
        exit(1)

    connection = get_db_connection()
    try:
        process_esdc_data(args.csv_file, connection)
    finally:
        connection.close()