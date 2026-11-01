import os
import argparse
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from rapidfuzz import fuzz, process
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
    query = "SELECT job_id, employer, location, noc_code FROM job_listings;"
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    
    # Structure: { noc_code: [ {job_id, employer, location}, ... ] }
    # Grouping by NOC speeds up the fuzzy matching process significantly.
    listings_by_noc = {}
    for row in rows:
        job_id, employer, location, noc_code = row
        if noc_code not in listings_by_noc:
            listings_by_noc[noc_code] = []
        listings_by_noc[noc_code].append({
            "job_id": job_id,
            "employer": employer,
            "location": location
        })
    return listings_by_noc

def process_esdc_data(csv_path: str, conn):
    """Reads the ESDC CSV, matches against Job Bank data, and inserts into esdc_approvals."""
    logger.info("loading_esdc_dataset", path=csv_path)
    
    # ESDC CSVs often have varying schemas depending on the quarter. 
    # Adjust these column names to match the exact headers of the downloaded open-data CSV.
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="ISO-8859-1")

    # Standardizing column names for internal processing
    col_map = {
        "Employer": "employer_name",
        "City": "city",
        "Province/Territory": "province",
        "NOC": "noc_code",
        "Approved Positions": "approved_positions"
    }
    
    # Rename columns if they exist in the dataframe
    df = df.rename(columns={col: col_map.get(col, col) for col in df.columns})
    
    # Clean NOC codes (sometimes they contain decimals or trailing text in the CSV)
    df["noc_code"] = df["noc_code"].astype(str).str.extract(r'(\d{4,5})')
    
    job_listings_db = fetch_job_listings(conn)
    records_to_insert = []
    match_count = 0

    for index, row in df.iterrows():
        employer = str(row.get("employer_name", "Unknown")).strip()
        city = str(row.get("city", "")).strip()
        province = str(row.get("province", "")).strip()
        noc = str(row.get("noc_code", "")).strip()
        positions = row.get("approved_positions", 1)
        
        # Clean up NaNs
        if pd.isna(positions): positions = 1
        
        location_str = f"{city}, {province}".strip(", ")
        matched_job_id = None
        
        # Cross-Reference Logic: If we have scraped jobs with this exact NOC, fuzzy match the Employer
        if noc in job_listings_db:
            candidates = job_listings_db[noc]
            employer_names = [c["employer"] for c in candidates]
            
            # Find the best string match for the employer name
            best_match = process.extractOne(employer, employer_names, scorer=fuzz.token_sort_ratio)
            
            if best_match and best_match[1] >= FUZZY_MATCH_THRESHOLD:
                matched_index = best_match[2]
                matched_job_id = candidates[matched_index]["job_id"]
                match_count += 1
                logger.info("positive_lmia_match_found", 
                            esdc_employer=employer, 
                            job_bank_employer=best_match[0], 
                            noc=noc, 
                            job_id=matched_job_id)
        
        records_to_insert.append((
            employer, 
            location_str, 
            noc, 
            int(positions), 
            "2026-Q3", # Hardcoded for now; can be parsed from filename/args later
            matched_job_id
        ))

    logger.info("reconciliation_complete", total_rows=len(df), matched_to_job_bank=match_count)

    # Insert into database
    query = """
        INSERT INTO esdc_approvals (
            employer_name, location, noc_code, approved_positions, quarter, matched_job_id
        ) VALUES %s
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