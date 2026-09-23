import feedparser
from dateutil import parser as date_parser
from datetime import datetime, timezone
from .dedupe import clean_text

def parse_datetime(entry):
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = date_parser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)

def fetch_feed(rss_url):
    return feedparser.parse(rss_url)