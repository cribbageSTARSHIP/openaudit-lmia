import asyncio
import re
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
        await page.wait_for_timeout(1000)

        # 1. Job Bank ID extraction
        job_id = fallback_id
        if not job_id or job_id == "unknown":
            match = re.search(r"(\d{7,9})", page.url)
            if match:
                job_id = match.group(1)
            else:
                body_text = await page.inner_text("body")
                id_match = re.search(r"(?:Job Bank\s*(?:job\s*posting)?\s*#?|Job\s*#)\s*(\d{7,9})", body_text, re.IGNORECASE)
                if id_match:
                    job_id = id_match.group(1)

        # 2. Title
        title_el = await page.query_selector("h1 span[property='title'], h1.title, h1 span[itemprop='title']")
        if not title_el:
            title_el = await page.query_selector("h1")
        raw_title = (await title_el.inner_text()).strip() if title_el else "Unknown"
        title = re.sub(r"\s+", " ", raw_title.replace("LMIA requested", "")).strip()

        # 3. Employer Name
        emp_el = await page.query_selector("span[property='hiringOrganization'] strong, span.business-name, span[itemprop='name'] strong")
        if not emp_el:
            emp_el = await page.query_selector("span.business-name, span[itemprop='name']")
        employer = (await emp_el.inner_text()).strip() if emp_el else "Unknown"

        # 4. Location
        loc_el = await page.query_selector("span[property='addressLocality'], ul.job-posting-brief li:has-text('Location')")
        raw_loc = (await loc_el.inner_text()).strip() if loc_el else "Unknown"
        location = " ".join([line.strip() for line in raw_loc.replace("Location", "").splitlines() if line.strip()])

        # 5. Wage
        wage_el = await page.query_selector("span[property='baseSalary'], ul.job-posting-brief li:has-text('HOUR'), ul.job-posting-brief li:has-text('Salary')")
        raw_wage = (await wage_el.inner_text()).strip() if wage_el else None
        wage = " ".join(raw_wage.replace("Salary", "").split()) if raw_wage else None

        # 6. NOC Code (search anchors linking to NOC trend analysis or NOC patterns)
        noc_code = None
        noc_link = await page.query_selector("a[href*='/noc/'], a[href*='noc=']")
        if noc_link:
            href = await noc_link.get_attribute("href") or ""
            noc_match = re.search(r"\b(\d{4,5})\b", href)
            if noc_match:
                noc_code = noc_match.group(1)

        if not noc_code:
            page_content = await page.content()
            # Match 4 or 5 digit NOC codes often prefixed by NOC or NOC 2021
            noc_match = re.search(r"NOC\s*(?:2021|2016)?\s*[:#-]?\s*(\d{4,5})", page_content, re.IGNORECASE)
            if noc_match:
                noc_code = noc_match.group(1)

        # 7. Contact / Apply Email
        email = None
        how_to_apply_btn = await page.query_selector("#howtoapply, button[aria-controls='howtoapplyDiv'], a#howtoapply")
        if how_to_apply_btn:
            try:
                await how_to_apply_btn.scroll_into_view_if_needed()
                await how_to_apply_btn.click()
                await page.wait_for_timeout(2000)
            except Exception:
                pass

        apply_container = await page.query_selector("#howtoapplyDiv, #howtoapplyContent, div.howtoapply")
        if apply_container:
            apply_text = await apply_container.inner_text()
            email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", apply_text)
            if email_match:
                email = email_match.group(1)

        # Fallback mailto search across full page DOM
        if not email:
            full_html = await page.content()
            mailto_match = re.search(r"mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", full_html)
            if mailto_match:
                email = mailto_match.group(1)

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
        await page.wait_for_selector("article, a.resultJobItem", timeout=15000)

        # Retrieve card elements
        articles = await page.query_selector_all("article")
        job_targets = []

        for art in articles:
            if len(job_targets) >= limit:
                break

            # Try to grab ID from article id (e.g. article-43892104)
            art_id = await art.get_attribute("id") or ""
            id_match = re.search(r"(\d{7,9})", art_id)
            card_id = id_match.group(1) if id_match else "unknown"

            # Grab the link
            link_el = await art.query_selector("a.resultJobItem, a")
            if link_el:
                href = await link_el.get_attribute("href") or ""
                if "/jobposting/" in href or "/jobsearch/jobposting" in href:
                    full_url = f"https://www.jobbank.gc.ca{href}" if href.startswith("/") else href
                    if card_id == "unknown":
                        url_match = re.search(r"jobposting/(\d{7,9})", full_url)
                        card_id = url_match.group(1) if url_match else "unknown"
                    job_targets.append((card_id, full_url))

        logger.info("found_listings", count=len(job_targets))

        # Parse each target detail page
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
    print("\n==========================================")
    print(f"Successfully parsed {len(records)} LMIA listings:")
    print("==========================================")
    for r in records:
        print(f"[{r.job_id}] {r.title} | Employer: {r.employer} | Loc: {r.location} | NOC: {r.noc_code} | Email: {r.how_to_apply_email}")