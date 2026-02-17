"""
Job application automation for Greenhouse, Lever, Ashby, and similar ATS boards.

- Fills application forms from config (name, email, phone, LinkedIn, resume, cover letter).
- User completes any custom questions and submits in the browser, then presses Enter to continue.
- Tracks applied jobs, supports resume, logs applications, and auto-detects board from URL.
"""

import json
import time
import os
import random
from datetime import datetime

from playwright.sync_api import sync_playwright

from boards import BOARDS, detect_board_from_url, get_board, get_search_site

# ---------------------------------------------------------------------------
# State file names (created/updated in the script directory)
# ---------------------------------------------------------------------------
APPLIED_JOBS_FILE = "applied_jobs.json"  # URLs we've already applied to (skip on next run)
PROGRESS_FILE = "progress.json"          # Current run's job list + last index (for --resume)
APPLICATIONS_LOG = "applications.log"    # Append-only log: timestamp, board, company, title, URL


def load_config():
    """Load config.json (personal info, resume path, search query, board, cover letter template)."""
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Applied jobs tracking (avoid applying twice to the same URL)
# ---------------------------------------------------------------------------
def load_applied_jobs() -> set:
    """Return set of job URLs we've already applied to. Empty set if file missing or invalid."""
    if not os.path.exists(APPLIED_JOBS_FILE):
        return set()
    try:
        with open(APPLIED_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("urls", []))
    except Exception:
        return set()


def save_applied_job(url: str):
    """Append this URL to applied_jobs.json so we skip it on future runs."""
    applied = load_applied_jobs()
    applied.add(url)
    with open(APPLIED_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump({"urls": list(applied)}, f, indent=2)


# ---------------------------------------------------------------------------
# Progress (for --resume: continue from last job in the same run)
# ---------------------------------------------------------------------------
def load_progress():
    """Load progress.json; returns None if missing or invalid. Contains job_urls and last_index."""
    if not os.path.exists(PROGRESS_FILE):
        return None
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_progress(job_urls: list, last_index: int):
    """Save current job list and index so we can resume with --resume after interruption."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"job_urls": job_urls, "last_index": last_index}, f, indent=2)


def clear_progress():
    """Remove progress.json when a run completes normally."""
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


def log_application(url: str, job_title: str, company: str, board_name: str):
    """Append one line to applications.log (timestamp, board, company, title, URL)."""
    line = f"{datetime.now().isoformat()}\t{board_name}\t{company}\t{job_title}\t{url}\n"
    with open(APPLICATIONS_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"   - Logged to {APPLICATIONS_LOG}")


def human_delay(min_s=1, max_s=3):
    """Random short delay to mimic human behavior and reduce detection risk."""
    time.sleep(random.uniform(min_s, max_s))


# ---------------------------------------------------------------------------
# Search: open DuckDuckGo in browser and collect job links for the given board
# ---------------------------------------------------------------------------
def search_jobs_via_browser(page, query: str, board_id: str = "all") -> list:
    """Use DuckDuckGo in the browser to collect job links.
    
    If board_id is 'all' (default), searches for all defined boards using an OR query.
    Otherwise, searches only for the specified board.
    Returns up to 20 URLs.
    """
    if board_id == "all":
        # Construct a combined query: (site:A OR site:B) query
        sites = [b["search_site"].replace("site:", "") for b in BOARDS.values()]
        site_query = " OR ".join([f"site:{site}" for site in sites])
        full_query = f"({site_query}) {query}"
        print(f"Searching ALL boards: {full_query} via browser...")
    else:
        # Specific board search
        search_site = get_search_site(board_id)
        full_query = f"{search_site} {query}"
        print(f"Searching {board_id}: {full_query} via browser...")

    # Go to DDG
    page.goto(f"https://duckduckgo.com/?q={full_query.replace(' ', '+')}&t=h_&ia=web")
    human_delay(2, 4)

    results = []
    # Collect links matching ANY known board pattern
    # usage of wait_for_selector ensures results are loaded
    try:
        page.wait_for_selector('a[href*="http"]', timeout=5000)
    except:
        pass

    found_links = page.query_selector_all('a[href]')
    
    for link in found_links:
        href = link.get_attribute("href")
        if not href:
            continue
            
        # Check against the requested board(s)
        for bid, board in BOARDS.items():
            # If we asked for a specific board, skip others
            if board_id != "all" and bid != board_id:
                continue
                
            # Check if link matches this board's patterns
            if all(p in href for p in board["url_patterns"]):
                if href not in results:
                    results.append(href)
                break # Matched a board, move to next link

    return results[:20]


# ---------------------------------------------------------------------------
# Job page: extract title/company and fill form using board-specific selectors
# ---------------------------------------------------------------------------
def get_job_context(page, board: dict) -> tuple[str, str]:
    """Extract job title and company name from the page using the board's selectors. Returns (title, company)."""
    title, company = "Unknown role", "Unknown company"
    for sel in board.get("job_title_selectors", []):
        try:
            el = page.query_selector(sel)
            if el:
                t = (el.inner_text() or "").strip()
                if t and len(t) < 200:
                    title = t
                    break
        except Exception:
            continue
    for sel in board.get("company_selectors", []):
        try:
            el = page.query_selector(sel)
            if el:
                c = (el.inner_text() or el.get_attribute("alt") or "").strip()
                if c and len(c) < 200:
                    company = c
                    break
        except Exception:
            continue
    return title, company


def fill_cover_letter_template(template: str, job_title: str, company: str) -> str:
    """Replace {job_title}, {company_name}, {company} in the template with actual values."""
    return (
        template.replace("{job_title}", job_title)
        .replace("{company_name}", company)
        .replace("{company}", company)
    )


def find_form(page, board: dict):
    """Locate the application form on the main page or inside an iframe (e.g. Greenhouse). Returns (form, page_or_frame)."""
    form_selector = board.get("form_selector", "form")
    # Try main document first
    try:
        form = page.wait_for_selector(form_selector, timeout=3000)
        if form:
            return form, page
    except Exception:
        pass

    # If board uses an iframe (e.g. Greenhouse), search frames
    if board.get("form_in_iframe"):
        for frame in page.frames:
            try:
                form = frame.wait_for_selector(form_selector, timeout=1000)
                if form:
                    return form, frame
            except Exception:
                pass
    return None, None


def fill_field(page_or_frame, field_key: str, value: str, board: dict, config: dict) -> bool:
    """Try each CSS selector for this field in order; fill and return True on first match. Returns False if no selector matches or value is empty."""
    if not value:
        return False
    fields_config = board.get("fields", {})
    selectors = fields_config.get(field_key, [])
    if not selectors:
        return False
    for sel in selectors:
        try:
            el = page_or_frame.query_selector(sel)
            if el:
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def fill_form_with_board(page_or_frame, board: dict, config: dict, job_title: str, company: str):
    """Fill all standard fields (name, email, phone, LinkedIn, cover letter, resume) using the board's selectors."""
    # Name: try first/last, then full "name" (Lever/Ashby sometimes use one field)
    full_name = f"{config.get('first_name', '')} {config.get('last_name', '')}".strip()
    fill_field(page_or_frame, "first_name", config.get("first_name", ""), board, config)
    fill_field(page_or_frame, "last_name", config.get("last_name", ""), board, config)
    if full_name:
        fill_field(page_or_frame, "name", full_name, board, config)
    fill_field(page_or_frame, "email", config.get("email", ""), board, config)
    fill_field(page_or_frame, "phone", config.get("phone", ""), board, config)

    # LinkedIn: use label text if board defines it (e.g. Greenhouse), else try selectors
    linkedin = config.get("linkedin_url", "")
    if linkedin:
        if board.get("linkedin_label"):
            try:
                inp = page_or_frame.get_by_label(board["linkedin_label"])
                if inp.count() > 0:
                    inp.fill(linkedin)
            except Exception:
                fill_field(page_or_frame, "linkedin_url", linkedin, board, config)
        else:
            fill_field(page_or_frame, "linkedin_url", linkedin, board, config)

    # Cover letter: substitute {job_title} and {company_name} from template
    cover = config.get("cover_letter") or config.get("cover_letter_template", "")
    if cover:
        cover = fill_cover_letter_template(cover, job_title, company)
        fill_field(page_or_frame, "cover_letter", cover, board, config)

    # Resume: set file on the first matching file input
    resume_path = config.get("resume_path", "")
    if resume_path and os.path.exists(resume_path):
        selectors = board.get("fields", {}).get("resume", ["input[type='file']"])
        for sel in selectors:
            try:
                page_or_frame.set_input_files(sel, resume_path)
                print(f"   - Uploaded resume from {resume_path}")
                break
            except Exception:
                continue
    else:
        if resume_path:
            print(f"   - WARNING: Resume not found at {resume_path}")


def apply_to_job(main_page, url: str, config: dict, board_id: str, index: int, total: int) -> bool:
    """Navigate to job URL, show role/company, find and fill form, wait for user to submit and press Enter. Records applied URL and logs to applications.log. Returns True if form was found and filled."""
    board = get_board(board_id)
    if not board:
        print(f"   - Unknown board for URL; skipping.")
        return False

    print(f"\n[{index}/{total}] Navigating to {url}...")
    main_page.goto(url)
    human_delay(2, 4)

    # Job context (use main page for title/company; they're usually not in iframe)
    job_title, company = get_job_context(main_page, board)
    print(f"   Role: {job_title}")
    print(f"   Company: {company}")

    form, form_page = find_form(main_page, board)
    if not form or not form_page:
        print("   - Application form not found.")
        try:
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(main_page.content())
            print("   - Dumped page to debug_page.html")
        except Exception as e:
            print(f"   - Could not dump page: {e}")
        return False

    print(f"   - Form found ({board['name']}). Filling...")
    fill_form_with_board(form_page, board, config, job_title, company)

    print("   - Form filled. Complete any custom questions and submit in the browser.")
    print("   - Press ENTER in this terminal when done to continue to the next job.")
    input("   >> Press Enter to continue... ")

    save_applied_job(url)
    log_application(url, job_title, company, board["name"])
    return True


# ---------------------------------------------------------------------------
# Entry point: load config, get job list (from config or search), then apply to each
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Apply to jobs on Greenhouse, Lever, Ashby, etc.")
    parser.add_argument("--resume", action="store_true", help="Resume from last progress (skip applied)")
    parser.add_argument("--board", choices=list(BOARDS.keys()) + ["all"], default=None, help="Board to search (default: all or from config)")
    args = parser.parse_args()

    config = load_config()
    applied = load_applied_jobs()

    # Decide job list source: manual URLs from config vs search (done later inside browser)
    job_urls = []
    from_search = False
    if config.get("job_urls"):
        job_urls = list(config["job_urls"])
        print(f"Using {len(job_urls)} job URLs from config.json")
        # Filter: either resume from last index or skip all already-applied URLs
        if args.resume:
            progress = load_progress()
            if progress and progress.get("job_urls") == job_urls:
                last = progress.get("last_index", -1)
                job_urls = job_urls[last + 1:]
                print(f"Resuming: {len(job_urls)} jobs remaining.")
            else:
                job_urls = [u for u in job_urls if u not in applied]
                print(f"Skipping {len(applied)} already applied; {len(job_urls)} jobs to process.")
        else:
            job_urls = [u for u in job_urls if u not in applied]
            if applied:
                print(f"Skipping {len(applied)} already applied; {len(job_urls)} jobs to process.")
            clear_progress()
    else:
        from_search = True  # We'll search in the browser and build job_urls there
        clear_progress()

    # If we already have URLs and the list is empty after filtering, exit before opening browser
    if not from_search and not job_urls:
        print("No jobs left to process.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # If not using config job_urls, run DuckDuckGo search and collect links
        if from_search:
            query = config.get("job_search_query", "engineer")
            board_id = args.board or config.get("board", "all")
            job_urls = search_jobs_via_browser(page, query, board_id)
            if not job_urls:
                print("No job links found. Exiting.")
                browser.close()
                return
            print(f"Found {len(job_urls)} job links.")
            job_urls = [u for u in job_urls if u not in applied]
            if applied:
                print(f"Skipping {len(applied)} already applied; {len(job_urls)} jobs to process.")

        if not job_urls:
            print("No jobs left to process.")
            browser.close()
            return

        total = len(job_urls)
        print(f"\nProcessing {total} job(s). Board is auto-detected from each URL.\n")

        # Process each job: detect board from URL, fill form, wait for user, then save progress
        for i, url in enumerate(job_urls):
            board_id = detect_board_from_url(url) or config.get("board", "greenhouse")
            apply_to_job(page, url, config, board_id, i + 1, total)
            save_progress(job_urls, i)

        clear_progress()
        print("\nAll jobs processed.")
        browser.close()


if __name__ == "__main__":
    main()
