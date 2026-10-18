import hashlib
import re


def clean_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def normalize_title(title):
    t = clean_text(title).lower()
    t = re.sub(r"[^\w\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()

def is_web_url(url):
    """True only for an http(s) link. Feed links are third-party input: a
    "javascript:" or "data:" link would survive HTML escaping and run when a
    reader clicked it on the site."""
    return bool(re.match(r"https?://[^\s/]", clean_text(url), re.I))

def standardize_url(url):
    u = clean_text(url)
    if not u:
        return u
    u = u.split("#", 1)[0]
    u = u.split("?", 1)[0]
    return u

def make_identifier(url, title):
    key = (standardize_url(url) + "||" + normalize_title(title)).encode("utf-8")
    return hashlib.sha256(key).hexdigest()