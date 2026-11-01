-- Table 1: Scraped Job Bank Listings
CREATE TABLE IF NOT EXISTS job_listings (
    job_id VARCHAR(50) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    employer VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    wage VARCHAR(100),
    noc_code VARCHAR(10),
    posting_url TEXT NOT NULL,
    is_lmia_flagged BOOLEAN DEFAULT TRUE,
    how_to_apply_email VARCHAR(255),
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Table 2: Verified Domestic Applicants
CREATE TABLE IF NOT EXISTS applicants (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(50) REFERENCES job_listings(job_id) ON DELETE CASCADE,
    resume_hash VARCHAR(64) NOT NULL,
    qualification_score NUMERIC(5,2),
    status VARCHAR(50) DEFAULT 'delivered',
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    delivery_receipt TEXT
);

-- Table 3: ESDC Positive LMIA Open Data
CREATE TABLE IF NOT EXISTS esdc_approvals (
    id SERIAL PRIMARY KEY,
    employer_name VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    noc_code VARCHAR(10),
    approved_positions INTEGER,
    quarter VARCHAR(10),
    matched_job_id VARCHAR(50) REFERENCES job_listings(job_id) ON DELETE SET NULL,
    imported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast cross-referencing
CREATE INDEX idx_job_listings_employer ON job_listings(employer);
CREATE INDEX idx_job_listings_noc ON job_listings(noc_code);
CREATE INDEX idx_esdc_approvals_employer ON esdc_approvals(employer_name);