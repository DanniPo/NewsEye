from datetime import UTC, datetime

import feedparser
from dateutil import parser as date_parser


def parse_datetime(entry):
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = date_parser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
            except Exception:
                pass
    return datetime.now(UTC)

def fetch_feed(rss_url):
    return feedparser.parse(rss_url)