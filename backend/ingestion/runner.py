import time
from backend.config import (
    ARTICLES_PER_FEED, RSS_FEEDS, EMBED_MAX_CHARS, FETCH_FULL_TEXT,
)
from backend.ingestion.rss import fetch_feed, parse_datetime
from backend.ingestion.dedupe import clean_text, standardize_url, make_identifier
from backend.ingestion.fetch import fetch_many, build_embed_text
from backend.nlp.embeddings import generate_embeddings_batch
from backend.nlp.classification import classify_topics_batch
from backend.db.queries import insert_article, article_exists


def run_ingestion():
    started = time.time()
    total_inserted = 0
    for feed_config in RSS_FEEDS:
        source_name = feed_config["name"]
        # header only printed if the feed yields something new (below)
        parsed = fetch_feed(feed_config["rss_url"])

        new_articles = []
        for i, entry in enumerate(parsed.entries[:ARTICLES_PER_FEED], start=1):
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
                       for a, body in zip(new_articles, bodies)]
        embeddings = generate_embeddings_batch(embed_texts)
        categories = classify_topics_batch([a["title"] for a in new_articles])

        for article, embedding, (category, _) in zip(new_articles, embeddings, categories):
            inserted = insert_article(article["identifier"], source_name, article["title"], article["url"],
                                       article["url_canon"], article["published"], article["snippet"],
                                       embedding, category)
            total_inserted += inserted

    print(f"Inserted {total_inserted} new articles in {time.time() - started:.1f}s")

if __name__ == "__main__":
    run_ingestion()