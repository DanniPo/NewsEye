"""Transient full-text fetching: used by the active tier, never stored."""
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import trafilatura

from backend.config import (
    FETCH_CONCURRENCY,
    FETCH_DELAY_SECONDS,
    MIN_BODY_CHARS,
)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewseyeBot/1.0)"}

# A paywall stub extracts to a few hundred characters of upsell. Length alone
# cannot separate it from a genuinely short article: Business Daily's 494-char
# piece on supply-chain exposure was real reporting, while its 339-char one was
# "Renew in to keep enjoying all our premium content". Detect the upsell instead.
PAYWALL = re.compile(
    r"to keep enjoying|premium content|don'?t have an account"
    r"|subscribe to continue|register to continue|create an account to"
    r"|this article is for subscribers|sign up to read", re.I)
TIMEOUT = 15

def fetch_article_text(url):
    try:
        response = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        response.raise_for_status()
        text = trafilatura.extract(
            response.text,
            include_formatting=False,
            include_links=False,
            include_comments=False,
            output_format="txt",
        )
        body = (text or "").strip()
        if PAYWALL.search(body[:400]):
            return ""
        # A video page or a 403 interstitial extracts to a few hundred characters
        # of navigation. Treating that as article text is worse than admitting we
        # could not read it: the claims come out as the site's own furniture.
        return body if len(body) >= MIN_BODY_CHARS else ""
    except Exception:
        return ""

def _polite_fetch(url):
    time.sleep(FETCH_DELAY_SECONDS)
    return fetch_article_text(url)

def fetch_many(urls):
    # low concurrency plus a delay: bulk parallel fetching gets the IP rate-limited
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        return list(pool.map(_polite_fetch, urls))

def build_embed_text(title, snippet, body, max_chars):
    parts = [title, body or snippet or ""]
    return " ".join(p for p in parts if p).strip()[:max_chars]
