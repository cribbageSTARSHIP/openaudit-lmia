import asyncio
import re
import sys
from typing import List, Optional
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, Browser, Page
import structlog

logger = structlog.get_logger()

# Job Bank search endpoint filtering for Temporary Foreign Worker Program / LMIA postings
JOB_BANK_SEARCH_URL = "https://www.jobbank.gc.ca/jobsearch/jobsearch?fsrc=32"


class JobListing(BaseModel):
    job_id: str = Field(..., description="Unique Job Bank posting ID")
    title: str
    employer: str
    location: str
    wage: Optional[str] = None
    noc_code: Optional[str] = None
    posting_url: str
    is_lmia_flagged: bool = True
    how_to_apply_email: Optional[str] = None


async def parse_job_details(page: Page, url: str, job_id: str) -> Optional[JobListing]:
    """Extracts detailed metadata from an individual Job Bank listing page."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)

        # Title
        title_el = await page.query_selector("span[itemprop='title']")
        title = (await title_el.inner_text()).strip() if title_el else "Unknown"

        # Employer operating/legal name
        emp_el = await page.query_selector("span[itemprop='name'] strong")
        employer = (await emp_el.inner_text()).strip() if emp_el else "Unknown"

        # Location
        loc_el = await page.query_selector("span[property='addressLocality']")
        location = (await loc_el.inner_text()).strip() if loc_el else "Unknown"

        # Wage
        wage_el = await page.query_selector("span[property='baseSalary']")
        wage = (await wage_el.inner_text()).strip() if wage_el else None

        # NOC Code extraction (usually located in the job summary table or footer metadata)
        body_text = await page.inner_text("body")
        noc_match = re.search(r"NOC\s*(\d{4,5})", body_text, re.IGNORECASE)
        noc_code = noc_match.group(1) if noc_match else None

        # Trigger 'How to apply' drawer if present to expose direct email
        how_to_apply_btn = await page.query_selector("#howtoapply")
        email = None
        if how_to_apply_btn:
            await how_to_apply_btn.click()
            await page.wait_for_timeout(1000)
            apply_section = await page.query_selector("#howtoapplyDiv")
            if apply_section:
                apply_text = await apply_section.inner_text()
                email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", apply_text)
                if email_match:
                    email = email_match.group(0)

        return JobListing(
            job_id=job_id,
            title=title,
            employer=employer,
            location=location,
            wage=wage,
            noc_code=noc_code,
            posting_url=url,
            is_lmia_flagged=True,
            how_to_apply_email=email,
        )
    except Exception as exc:
        logger.error("error_parsing_job_detail", job_id=job_id, url=url, error=str(exc))
        return None


async def run_scraper(limit: int = 25) -> List[JobListing]:
    """Discovers LMIA postings on Job Bank and extracts structured records."""
    results: List[JobListing] = []

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page: Page = await context.new_page()

        logger.info("navigating_to_job_bank", url=JOB_BANK_SEARCH_URL)
        await page.goto(JOB_BANK_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)

        # Locate job card links
        cards = await page.query_selector_all("a.resultJobItem")
        job_targets = []

        for card in cards[:limit]:
            href = await card.get_attribute("href")
            if href:
                full_url = f"https://www.jobbank.gc.ca{href}" if href.startswith("/") else href
                job_id_match = re.search(r"/jobposting/(\d+)", full_url)
                job_id = job_id_match.group(1) if job_id_match else "unknown"
                job_targets.append((job_id, full_url))

        logger.info("found_listings", count=len(job_targets))

        # Parse listings
        for job_id, url in job_targets:
            listing = await parse_job_details(page, url, job_id)
            if listing:
                results.append(listing)
                logger.info(
                    "listing_ingested",
                    job_id=listing.job_id,
                    title=listing.title,
                    employer=listing.employer,
                    email=listing.how_to_apply_email,
                )

        await browser.close()

    return results


if __name__ == "__main__":
    records = asyncio.run(run_scraper(limit=10))
    print(f"\nSuccessfully parsed {len(records)} LMIA listings.")
    for r in records:
        print(f"[{r.job_id}] {r.title} at {r.employer} ({r.location}) | NOC: {r.noc_code} | Apply: {r.how_to_apply_email}")