"""Semantic search over the corpus, and over the stories built from it.

Every article already carries a MiniLM embedding and the table already has an
HNSW cosine index, so search is a query rather than a new subsystem: embed the
phrase, ask Postgres for nearest neighbours, and let the index do the work.

Two shapes, because readers and researchers want different things:

    search_articles("police shot protesters")   -> individual articles
    search_stories("police shot protesters")    -> clusters, ranked by their
                                                   best-matching member

For a media literacy site the second is the useful one. A reader looking for
"housing levy" wants the story several outlets covered, not twelve separate
copies of it.

    python -m backend.nlp.search "police killed protesters"
    python -m backend.nlp.search --articles "housing levy"
"""
import argparse

from backend.db.connection import get_cursor


def _vector_literal(values):
    """pgvector accepts a bracketed list; psycopg2 has no native adapter here."""
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def embed_query(text):
    from backend.nlp.embeddings import generate_embedding
    return _vector_literal(generate_embedding(text))


def search_articles(query, limit=20, max_distance=0.75):
    """Nearest articles by cosine distance. Lower distance is closer."""
    vector = embed_query(query)
    with get_cursor() as cur:
        cur.execute("""
            SELECT a.id, a.title, a.source_name, a.url, a.published_utc,
                   a.category, cm.cluster_id,
                   a.embedding <=> %s::vector AS distance
            FROM articles a
            LEFT JOIN cluster_members cm ON cm.article_id = a.id
            WHERE a.embedding IS NOT NULL
            ORDER BY a.embedding <=> %s::vector
            LIMIT %s
        """, (vector, vector, limit))
        return [r for r in cur.fetchall() if r["distance"] <= max_distance]


def search_stories(query, limit=10, candidates=120, max_distance=0.75):
    """Clusters ranked by their closest member.

    Searching articles and rolling up beats embedding the cluster itself: a
    cluster has no single text, and its best-matching article is exactly the one
    a reader would want to see quoted in the result.
    """
    vector = embed_query(query)
    with get_cursor() as cur:
        cur.execute("""
            WITH near AS (
                SELECT a.id, a.title, a.source_name,
                       cm.cluster_id,
                       a.embedding <=> %s::vector AS distance
                FROM articles a
                JOIN cluster_members cm ON cm.article_id = a.id
                WHERE a.embedding IS NOT NULL
                ORDER BY a.embedding <=> %s::vector
                LIMIT %s
            )
            SELECT n.cluster_id,
                   min(n.distance) AS distance,
                   count(*) AS matched_articles,
                   c.article_count, c.coherence, c.topic_label,
                   ca.title_summary,
                   count(DISTINCT a2.source_name) AS sources,
                   (array_agg(n.title ORDER BY n.distance))[1] AS best_title,
                   (array_agg(n.source_name ORDER BY n.distance))[1] AS best_source
            FROM near n
            JOIN clusters c ON c.id = n.cluster_id
            LEFT JOIN cluster_analysis ca ON ca.cluster_id = c.id
            JOIN cluster_members cm2 ON cm2.cluster_id = c.id
            JOIN articles a2 ON a2.id = cm2.article_id
            GROUP BY n.cluster_id, c.article_count, c.coherence, c.topic_label,
                     ca.title_summary
            ORDER BY min(n.distance)
            LIMIT %s
        """, (vector, vector, candidates, limit))
        return [r for r in cur.fetchall() if r["distance"] <= max_distance]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+")
    parser.add_argument("--articles", action="store_true",
                        help="return individual articles instead of stories")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    query = " ".join(args.query)

    if args.articles:
        rows = search_articles(query, limit=args.limit)
        print(f'{len(rows)} articles for "{query}"')
        for row in rows:
            cluster = f"c{row['cluster_id']}" if row["cluster_id"] else "-"
            print(f"  {row['distance']:.3f}  [{(row['source_name'] or '?')[:18]:<18}] "
                  f"{cluster:<5} {row['title'][:66]}")
        return

    rows = search_stories(query, limit=args.limit)
    print(f'{len(rows)} stories for "{query}"')
    for row in rows:
        coherence = f"{row['coherence']:.2f}" if row["coherence"] is not None else " - "
        print(f"\n  {row['distance']:.3f}  cluster {row['cluster_id']} | "
              f"{row['sources']} outlets | {row['article_count']} articles | coh {coherence}")
        print(f"          {(row['title_summary'] or row['best_title'])[:82]}")
        print(f"          best match: [{row['best_source']}] {row['best_title'][:62]}")


if __name__ == "__main__":
    main()
