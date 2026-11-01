import asyncio
import re
import sys
from typing import List, Optional
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, Browser, Page
import structlog

logger = structlog.get_logger()

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


async def parse_job_details(page: Page, url: str, fallback_id: str) -> Optional[JobListing]:
    """Extracts detailed metadata from an individual Job Bank listing page."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 1. Job Bank ID extraction from URL or DOM
        url_id_match = re.search(r"/jobposting/(\d+)", page.url)
        if url_id_match:
            job_id = url_id_match.group(1)
        else:
            id_el = await page.query_selector("span#jobpostid, [property='identifier']")
            job_id = (await id_el.inner_text()).strip() if id_el else fallback_id

        # 2. Job Title
        title_el = await page.query_selector("h1 span[property='title'], h1.title, h1 span[itemprop='title']")
        if not title_el:
            title_el = await page.query_selector("h1")
        title = (await title_el.inner_text()).strip() if title_el else "Unknown"

        # 3. Employer Name
        emp_el = await page.query_selector("span[property='hiringOrganization'] strong, span.business-name, span[itemprop='name']")
        employer = (await emp_el.inner_text()).strip() if emp_el else "Unknown"

        # 4. Location
        loc_el = await page.query_selector("span[property='addressLocality'], span.city, ul.job-posting-brief li:has-text('Location')")
        location = (await loc_el.inner_text()).strip() if loc_el else "Unknown"
        location = location.replace("Location", "").strip()

        # 5. Wage
        wage_el = await page.query_selector("span[property='baseSalary'], ul.job-posting-brief li:has-text('HOUR'), ul.job-posting-brief li:has-text('Salary')")
        wage = (await wage_el.inner_text()).strip() if wage_el else None
        if wage:
            wage = wage.replace("Salary", "").strip()

        # 6. NOC Code (Extract 4 or 5 digit code)
        body_text = await page.inner_text("body")
        noc_match = re.search(r"NOC\s*(\d{4,5})", body_text, re.IGNORECASE)
        noc_code = noc_match.group(1) if noc_match else None

        # 7. Contact / Apply Email via 'How to Apply' button
        email = None
        how_to_apply_btn = await page.query_selector("button#howtoapply, a#howtoapply, #howtoapply")
        if how_to_apply_btn:
            try:
                await how_to_apply_btn.click()
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        apply_content = await page.query_selector("#howtoapplyDiv, #howtoapplyContent, div.howtoapply")
        if apply_content:
            apply_text = await apply_content.inner_text()
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", apply_text)
            if email_match:
                email = email_match.group(0)

        # Fallback search for email across the page
        if not email:
            email_match = re.search(r"mailto:([\w\.-]+@[\w\.-]+\.\w+)", await page.content())
            if email_match:
                email = email_match.group(1)

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
        logger.error("error_parsing_job_detail", url=url, error=str(exc))
        return None


async def run_scraper(limit: int = 10) -> List[JobListing]:
    """Discovers LMIA postings on Job Bank and extracts structured records."""
    results: List[JobListing] = []

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page: Page = await context.new_page()

        logger.info("navigating_to_job_bank", url=JOB_BANK_SEARCH_URL)
        await page.goto(JOB_BANK_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)

        # Locate job card links
        cards = await page.query_selector_all("article a.resultJobItem, a.resultJobItem")
        job_targets = []

        for card in cards[:limit]:
            href = await card.get_attribute("href")
            if href:
                full_url = f"https://www.jobbank.gc.ca{href}" if href.startswith("/") else href
                match = re.search(r"/jobposting/(\d+)", full_url)
                extracted_id = match.group(1) if match else "unknown"
                job_targets.append((extracted_id, full_url))

        logger.info("found_listings", count=len(job_targets))

        # Parse listings
        for fallback_id, url in job_targets:
            listing = await parse_job_details(page, url, fallback_id)
            if listing:
                results.append(listing)
                logger.info(
                    "listing_ingested",
                    job_id=listing.job_id,
                    title=listing.title,
                    employer=listing.employer,
                    location=listing.location,
                    noc=listing.noc_code,
                    email=listing.how_to_apply_email,
                )

        await browser.close()

    return results


if __name__ == "__main__":
    records = asyncio.run(run_scraper(limit=10))
    print(f"\n==========================================")
    print(f"Successfully parsed {len(records)} LMIA listings:")
    print(f"==========================================")
    for r in records:
        print(f"[{r.job_id}] {r.title} | Employer: {r.employer} | Loc: {r.location} | NOC: {r.noc_code} | Email: {r.how_to_apply_email}")