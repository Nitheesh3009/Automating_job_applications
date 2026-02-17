"""
Board (ATS) definitions for job application automation.

Each board entry defines:
- URL patterns: used to detect which board a job link belongs to
- search_site: DuckDuckGo site: query (e.g. site:boards.greenhouse.io)
- job_title_selectors / company_selectors: CSS selectors to extract role and company for display
- form_selector: CSS selector for the application form (tried on main page then in iframes if form_in_iframe)
- fields: map of field key -> list of CSS selectors (tried in order until one matches)
- linkedin_label: optional label text for LinkedIn (e.g. "LinkedIn Profile") when not using a selector
"""

# Config keys that map to form fields (used for validation/documentation)
CONFIG_KEYS = ["first_name", "last_name", "email", "phone", "linkedin_url", "resume_path", "cover_letter"]

# ---------------------------------------------------------------------------
# Board definitions: Greenhouse, Lever, Ashby (no-account apply flows)
# ---------------------------------------------------------------------------
BOARDS = {
    # ----- Greenhouse (boards.greenhouse.io) -----
    "greenhouse": {
        "id": "greenhouse",
        "name": "Greenhouse",
        "search_site": "site:boards.greenhouse.io",
        "url_patterns": ["boards.greenhouse.io", "/jobs/"],
        # Selectors to find job title and company on the job page (for display before filling)
        "job_title_selectors": [
            "h1.app-title",
            ".app-title",
            "h1",
            "[data-qa*='job-title']",
        ],
        "company_selectors": [
            ".company-name",
            ".app-company-name",
            "a.company-link",
            "[data-qa*='company']",
        ],
        "form_selector": "form#application-form",
        "form_in_iframe": True,  # Greenhouse often embeds the form in an iframe
        "fields": {
            # Each key: list of CSS selectors tried in order; first match is used
            "first_name": ["#first_name", "input[name='first_name']", "input[id*='first']"],
            "last_name": ["#last_name", "input[name='last_name']", "input[id*='last']"],
            "email": ["#email", "input[name='email']", "input[type='email']"],
            "phone": ["#phone", "input[name='phone']", "input[type='tel']"],
            "linkedin_url": ["#job_application_answers_attributes_0_text_value", "input[name*='linkedin']", "input[id*='linkedin']"],
            "resume": ["input[type='file'][name*='resume']", "input[type='file'][name*='content']", "input[type='file']"],
            "cover_letter": ["#job_application_cover_letter", "textarea[name*='cover']", "textarea[id*='cover']", "textarea[placeholder*='cover']"],
        },
        "linkedin_label": "LinkedIn Profile",  # Fallback: fill by label text if no selector matches
    },
    # ----- Lever (jobs.lever.co) -----
    "lever": {
        "id": "lever",
        "name": "Lever",
        "search_site": "site:jobs.lever.co",
        "url_patterns": ["jobs.lever.co"],
        "job_title_selectors": [
            "h2.posting-headline__title",
            ".posting-headline h2",
            "h1.posting-headline__title",
            "h2",
            "h1",
        ],
        "company_selectors": [
            ".posting-headline__company",
            ".main-header-logo img[alt]",
            "a.posting-header-logo",
            "h1 + div",
        ],
        "form_selector": "form.posting-form, form[action*='apply'], .postings-btn-wrapper + form",
        "form_in_iframe": False,
        "fields": {
            "name": ["input[name='name']", "input#name", "input[placeholder*='ame']"],  # Some Lever forms use single "name"
            "first_name": ["input[name='firstName']", "input#firstName", "input[name*='first']", "#first_name"],
            "last_name": ["input[name='lastName']", "input#lastName", "input[name*='last']", "#last_name"],
            "email": ["input[name='email']", "input#email", "input[type='email']"],
            "phone": ["input[name='phone']", "input#phone", "input[type='tel']"],
            "linkedin_url": ["input[name*='linkedin']", "input[name*='url']", "input[id*='linkedin']"],
            "resume": ["input[type='file']"],
            "cover_letter": ["textarea[name*='comments']", "textarea[name*='comment']", "textarea[name*='cover']", "textarea"],
        },
        "linkedin_label": None,
    },
    # ----- Ashby (jobs.ashbyhq.com) -----
    "ashby": {
        "id": "ashby",
        "name": "Ashby",
        "search_site": "site:jobs.ashbyhq.com",
        "url_patterns": ["jobs.ashbyhq.com"],
        "job_title_selectors": [
            "h1[data-ashby-job-title]",
            "h1.job-title",
            "h1",
        ],
        "company_selectors": [
            "[data-ashby-company-name]",
            ".company-name",
            "a[href*='ashbyhq.com']",
        ],
        "form_selector": "form[data-ashby-form], form",
        "form_in_iframe": False,
        "fields": {
            "name": ["input[name*='name']", "input[placeholder*='ame']"],
            "first_name": ["input[name*='firstName']", "input[name*='first_name']", "#first_name", "input[id*='first']"],
            "last_name": ["input[name*='lastName']", "input[name*='last_name']", "#last_name", "input[id*='last']"],
            "email": ["input[name*='email']", "input[type='email']", "#email"],
            "phone": ["input[name*='phone']", "input[type='tel']", "#phone"],
            "linkedin_url": ["input[name*='linkedin']", "input[name*='url']", "input[placeholder*='LinkedIn']"],
            "resume": ["input[type='file']"],
            "cover_letter": ["textarea[name*='cover']", "textarea[name*='letter']", "textarea"],
        },
        "linkedin_label": None,
    },
}


def detect_board_from_url(url: str) -> str | None:
    """Return board id (e.g. 'greenhouse') if URL matches a known board's url_patterns."""
    url_lower = url.lower()
    for bid, board in BOARDS.items():
        if all(p in url_lower for p in board["url_patterns"]):
            return bid
    return None


def get_board(board_id: str) -> dict | None:
    """Return the board config dict for the given id, or None."""
    return BOARDS.get(board_id)


def get_search_site(board_id: str) -> str:
    """Return the DuckDuckGo site: query string for the board (e.g. 'site:boards.greenhouse.io')."""
    return BOARDS.get(board_id, {}).get("search_site", "site:boards.greenhouse.io")
