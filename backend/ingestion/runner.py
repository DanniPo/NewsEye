import time

from backend.config import (
    ARTICLES_PER_FEED,
    EMBED_MAX_CHARS,
    FETCH_FULL_TEXT,
    RSS_FEEDS,
)
from backend.db.queries import article_exists, insert_article
from backend.ingestion.dedupe import clean_text, make_identifier, standardize_url
from backend.ingestion.fetch import build_embed_text, fetch_many
from backend.ingestion.rss import fetch_feed, parse_datetime
from backend.nlp.classification import classify_topics_batch
from backend.nlp.embeddings import generate_embeddings_batch


def run_ingestion():
    started = time.time()
    total_inserted = 0
    for feed_config in RSS_FEEDS:
        source_name = feed_config["name"]
        # header only printed if the feed yields something new (below)
        parsed = fetch_feed(feed_config["rss_url"])

        new_articles = []
        for entry in parsed.entries[:ARTICLES_PER_FEED]:
            title = clean_text(entry.get("title", ""))
            url = clean_text(entry.get("link", ""))
            snippet = clean_text(entry.get("summary", ""))[:150]
            if not title or not url:
                continue

            identifier = make_identifier(url, title)
            if article_exists(identifier):
                # every run re-reads the whole feed by design, so most items are
                # already known. Logging each one buried the real output under
                # ~300 lines a run once this started writing to a file.
                continue

            print(f"  + {title[:70]}")
            new_articles.append({
                "identifier": identifier,
                "title": title,
                "url": url,
                "url_canon": standardize_url(url),
                "published": parse_datetime(entry),
                "snippet": snippet,
            })

        if not new_articles:
            continue
        print(f"{source_name}: {len(new_articles)} new")

        bodies = [""] * len(new_articles)
        if FETCH_FULL_TEXT:
            bodies = fetch_many([a["url"] for a in new_articles])
            got = sum(1 for b in bodies if b)
            print(f"  fetched full text for {got}/{len(new_articles)}")

        # batch embeddings + classification across all new articles in this feed
        embed_texts = [build_embed_text(a["title"], a["snippet"], body, EMBED_MAX_CHARS)
                       for a, body in zip(new_articles, bodies, strict=True)]
        embeddings = generate_embeddings_batch(embed_texts)
        categories = classify_topics_batch([a["title"] for a in new_articles])

        for article, embedding, (category, _) in zip(new_articles, embeddings, categories, strict=True):
            inserted = insert_article(article["identifier"], source_name, article["title"], article["url"],
                                       article["url_canon"], article["published"], article["snippet"],
                                       embedding, category)
            total_inserted += inserted

    print(f"Inserted {total_inserted} new articles in {time.time() - started:.1f}s")

if __name__ == "__main__":
    run_ingestion()