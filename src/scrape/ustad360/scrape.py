#!/usr/bin/env python3
"""
Ustad360.com Past Papers PDF Scraper
=====================================
Scrapes and downloads all past paper PDFs from ustad360.com
for all Punjab board classes (9th, 10th, 11th, 12th).

Usage:
    python scrape_ustad360.py [--output-dir ./past_papers] [--classes 9 10 11 12]
                              [--delay 1.5] [--dry-run]

Requirements:
    pip install requests beautifulsoup4 lxml
"""

import argparse
import os
import re
import time
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.ustad360.com"

# Known past-paper index pages per class (Punjab boards)
CLASS_PAGES = {
    "9": "/past-papers/punjab/9th-class/",
    "10": "/past-papers/punjab/10th-class/",
    "11": "/past-papers/punjab/11th-class/",
    "12": "/past-papers/punjab/12th-class/",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_soup(session: requests.Session, url: str) -> BeautifulSoup | None:
    """Fetch a URL and return a BeautifulSoup object, or None on failure."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as exc:
        log.warning("Failed to fetch %s — %s", url, exc)
        return None


def sanitise(name: str) -> str:
    """Replace characters that are unsafe in file/folder names."""
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip()


def download_pdf(
    session: requests.Session,
    pdf_url: str,
    dest_path: Path,
    dry_run: bool = False,
) -> bool:
    """Download a single PDF.  Returns True on success."""
    if dest_path.exists():
        log.info("  SKIP (exists)  %s", dest_path.name)
        return True

    if dry_run:
        log.info("  DRY-RUN  →  %s", dest_path)
        return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with session.get(pdf_url, headers=HEADERS, timeout=60, stream=True) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    fh.write(chunk)
        log.info("  ✓  %s", dest_path.name)
        return True
    except requests.RequestException as exc:
        log.warning("  ✗  Download failed for %s — %s", pdf_url, exc)
        return False


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------


def find_subject_links(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """
    From a class-level index page, extract (subject_name, url) pairs.
    The page typically contains colourful card links to individual subject pages.
    """
    links = []
    # The subject cards are <a> tags that wrap a heading/div describing the subject
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Filter: must be an internal link that looks like a subject past-paper page
        if not href.startswith("http"):
            href = urljoin(base_url, href)
        parsed = urlparse(href)
        if parsed.netloc and "ustad360.com" not in parsed.netloc:
            continue
        path = parsed.path.lower()
        if "past-paper" in path and path != urlparse(base_url).path:
            text = a.get_text(" ", strip=True)
            if text and len(text) < 120:
                links.append((text, href))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for name, url in links:
        if url not in seen:
            seen.add(url)
            unique.append((name, url))
    return unique


def find_pdf_links(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """
    From a subject page, extract (filename, download_url) for every PDF.

    The page structure (from screenshots) shows:
      • A list of file entries, each with a filename label and a Download button
        whose href points directly to a .pdf file.
    """
    results = []

    # Strategy 1: <a> tags whose text contains "Download" and href ends in .pdf
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(base_url, href)
        if href.lower().endswith(".pdf"):
            filename = Path(urlparse(href).path).name or "file.pdf"
            results.append((filename, href))
            continue
        # Some sites serve PDFs via a redirect — catch download buttons too
        text = a.get_text(strip=True).lower()
        if "download" in text and ".pdf" in href.lower():
            filename = Path(urlparse(href).path).name or "file.pdf"
            results.append((filename, href))

    # Strategy 2: direct .pdf hrefs (covers inline links)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(base_url, href)
        if ".pdf" in href.lower() and (filename := Path(urlparse(href).path).name):
            results.append((filename, href))

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for name, url in results:
        if url not in seen_urls:
            seen_urls.add(url)
            unique.append((name, url))
    return unique


def scrape_subject_page(
    session: requests.Session,
    subject_name: str,
    subject_url: str,
    output_dir: Path,
    delay: float,
    dry_run: bool,
) -> int:
    """Scrape one subject page and download all PDFs found.  Returns count."""
    log.info("Subject: %s  (%s)", subject_name, subject_url)
    soup = get_soup(session, subject_url)
    if soup is None:
        return 0

    # Some sites paginate by year — look for "Load More" / year accordion sections
    # and also follow any additional paginated links found on the page.
    all_pdfs = find_pdf_links(soup, subject_url)

    # Check for year-section sub-links (accordion sections may lazy-load content)
    # Try to find any additional pages referenced on this page
    extra_pages: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(subject_url, href)
        parsed_path = urlparse(href).path.lower()
        if (
            "ustad360.com" in href
            and parsed_path != urlparse(subject_url).path.lower()
            and "past-paper" in parsed_path
            and href not in extra_pages
        ):
            extra_pages.append(href)

    for extra_url in extra_pages[:10]:  # safety cap
        extra_soup = get_soup(session, extra_url)
        if extra_soup:
            extra_pdfs = find_pdf_links(extra_soup, extra_url)
            seen = {u for _, u in all_pdfs}
            for name, url in extra_pdfs:
                if url not in seen:
                    all_pdfs.append((name, url))
                    seen.add(url)
        time.sleep(delay)

    if not all_pdfs:
        log.info("  No PDFs found on this page.")
        return 0

    log.info("  Found %d PDF(s)", len(all_pdfs))
    folder = output_dir / sanitise(subject_name)
    count = 0
    for filename, pdf_url in all_pdfs:
        dest = folder / sanitise(filename)
        if download_pdf(session, pdf_url, dest, dry_run=dry_run):
            count += 1
        time.sleep(delay)

    return count


def scrape_class(
    session: requests.Session,
    class_label: str,
    index_url: str,
    output_dir: Path,
    delay: float,
    dry_run: bool,
) -> int:
    """Scrape one class's past-paper index page, then each subject.  Returns total count."""
    log.info("=" * 60)
    log.info("Class %s  →  %s", class_label, index_url)
    log.info("=" * 60)

    soup = get_soup(session, index_url)
    if soup is None:
        log.error("Could not load class index page: %s", index_url)
        return 0

    subject_links = find_subject_links(soup, BASE_URL)
    if not subject_links:
        log.warning("No subject links found on %s", index_url)
        return 0

    log.info(
        "Found %d subject(s): %s",
        len(subject_links),
        ", ".join(n for n, _ in subject_links),
    )

    class_dir = output_dir / f"Class_{class_label}"
    total = 0
    for subject_name, subject_url in subject_links:
        total += scrape_subject_page(
            session, subject_name, subject_url, class_dir, delay, dry_run
        )
        time.sleep(delay)

    return total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape all past-paper PDFs from ustad360.com (Punjab boards)"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./past_papers",
        help="Root folder to save downloaded PDFs (default: ./past_papers)",
    )
    parser.add_argument(
        "--classes",
        "-c",
        nargs="+",
        default=["9", "10", "11", "12"],
        metavar="CLASS",
        help="Which classes to scrape, e.g.  --classes 9 10  (default: all)",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=1.5,
        help="Seconds to wait between requests (default: 1.5 — be polite!)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be downloaded without actually saving files",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output directory: %s", output_dir)

    if args.dry_run:
        log.info("*** DRY RUN — no files will be written ***")

    session = requests.Session()
    session.headers.update(HEADERS)

    grand_total = 0
    for cls in args.classes:
        if cls not in CLASS_PAGES:
            log.warning(
                "Unknown class '%s' — skipping. Valid: %s", cls, list(CLASS_PAGES)
            )
            continue
        index_url = BASE_URL + CLASS_PAGES[cls]
        grand_total += scrape_class(
            session, cls, index_url, output_dir, args.delay, args.dry_run
        )

    log.info("=" * 60)
    log.info(
        "Done!  Total PDFs %s: %d",
        "found" if args.dry_run else "downloaded",
        grand_total,
    )


if __name__ == "__main__":
    main()
