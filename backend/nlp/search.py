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

search_story_groups() goes one step further and sets related stories side by
side - the Dangote groundbreaking next to the court order halting it - without
merging them, since each is still its own comparison.

    python -m backend.nlp.search "police killed protesters"
    python -m backend.nlp.search --articles "housing levy"
    python -m backend.nlp.search --ungrouped "dangote refinery"
"""
import argparse

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from backend.config import RELATED_STORY_MAX_DISTANCE
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


def _parse_vector(value):
    # psycopg2 returns pgvector values as strings like "[0.1,0.2,...]"
    return np.array([float(x) for x in value.strip("[]").split(",")])


def cluster_centroids(cluster_ids):
    """Mean member embedding per cluster, averaged by pgvector itself."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT cm.cluster_id, avg(a.embedding) AS centroid
            FROM cluster_members cm
            JOIN articles a ON a.id = cm.article_id
            WHERE cm.cluster_id = ANY(%s) AND a.embedding IS NOT NULL
            GROUP BY cm.cluster_id
        """, (list(cluster_ids),))
        return {r["cluster_id"]: _parse_vector(r["centroid"]) for r in cur.fetchall()}


def group_related(stories, max_distance=RELATED_STORY_MAX_DISTANCE):
    """Gather ranked stories into groups of related ones, keeping rank order.

    Average linkage rather than single: single linkage chains A to B to C until
    a death notice and a football profile share a group because each resembled
    the next. Groups come back ordered by their best-ranked story, and stories
    within a group keep their own order.
    """
    if len(stories) < 2:
        return [[s] for s in stories]
    centroids = cluster_centroids(s["cluster_id"] for s in stories)
    vectors = np.array([centroids[s["cluster_id"]] for s in stories])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    labels = AgglomerativeClustering(
        n_clusters=None, metric="cosine", linkage="average",
        distance_threshold=max_distance,
    ).fit_predict(vectors)
    groups = {}
    for story, label in zip(stories, labels, strict=True):
        groups.setdefault(label, []).append(story)
    return list(groups.values())


def search_story_groups(query, limit=10, **kwargs):
    """search_stories(), with related stories grouped under one result."""
    return group_related(search_stories(query, limit=limit, **kwargs))


def _print_story(row, indent="  "):
    coherence = f"{row['coherence']:.2f}" if row["coherence"] is not None else " - "
    print(f"{indent}{row['distance']:.3f}  cluster {row['cluster_id']} | "
          f"{row['sources']} outlets | {row['article_count']} articles | coh {coherence}")
    print(f"{indent}        {(row['title_summary'] or row['best_title'])[:82]}")
    print(f"{indent}        best match: [{row['best_source']}] {row['best_title'][:62]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+")
    parser.add_argument("--articles", action="store_true",
                        help="return individual articles instead of stories")
    parser.add_argument("--ungrouped", action="store_true",
                        help="list stories one by one, without grouping related ones")
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

    if args.ungrouped:
        rows = search_stories(query, limit=args.limit)
        print(f'{len(rows)} stories for "{query}"')
        for row in rows:
            print()
            _print_story(row)
        return

    groups = search_story_groups(query, limit=args.limit)
    stories = sum(len(g) for g in groups)
    print(f'{stories} stories in {len(groups)} results for "{query}"')
    for group in groups:
        print()
        if len(group) == 1:
            _print_story(group[0])
            continue
        print(f"  related coverage - {len(group)} stories")
        for row in group:
            _print_story(row, indent="    ")


if __name__ == "__main__":
    main()
