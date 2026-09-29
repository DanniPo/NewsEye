"""Plot the clustering window in two dimensions.

    python -m backend.scripts.visualize_clusters
    python -m backend.scripts.visualize_clusters --topic Politics

Only the window that was clustered is drawn: articles older than it are never
clustered, so plotting them only adds grey. Colour marks cluster membership,
not cluster identity - with ~350 clusters no palette tells them apart, and the
previous version's one-legend-entry-per-cluster was unreadable. The largest
stories are named on the plot instead.

t-SNE rather than PCA: PCA keeps the two directions of greatest variance across
the whole corpus, which for 384-dim sentence embeddings piles every story on
top of the others. t-SNE keeps neighbours next to each other, which is the
property a cluster plot needs. Distances between far-apart groups mean little.
"""
import argparse
import textwrap

import matplotlib.pyplot as plt
import numpy as np
from sklearn.manifold import TSNE

from backend.config import CLUSTER_WINDOW_DAYS
from backend.db.connection import get_cursor
from backend.nlp.clustering import parse_embedding

OUTPUT_PATH = "cluster_visualization.png"
LABELLED_STORIES = 12

HIGHLIGHT = "#2a78d6"
OTHER = "#b9c3cf"
NOISE = "#dcdad3"


def load(window_days):
    with get_cursor() as cur:
        cur.execute("""
            SELECT a.embedding, cm.cluster_id, c.topic_label, ca.title_summary,
                   a.source_name
            FROM articles a
            LEFT JOIN cluster_members cm ON cm.article_id = a.id
            LEFT JOIN clusters c ON c.id = cm.cluster_id
            LEFT JOIN cluster_analysis ca ON ca.cluster_id = c.id
            WHERE a.embedding IS NOT NULL
              AND a.published_utc >= now() - %s::interval
        """, (f"{window_days} days",))
        return cur.fetchall()


def visualize_clusters(topic=None, window_days=CLUSTER_WINDOW_DAYS, output=OUTPUT_PATH):
    rows = load(window_days)
    embeddings = np.array([parse_embedding(r["embedding"]) for r in rows], dtype=float)
    cluster_ids = np.array([r["cluster_id"] or -1 for r in rows])
    print(f"Projecting {len(rows)} articles from the last {window_days} days...")
    coords = TSNE(n_components=2, metric="cosine", init="pca",
                  random_state=0).fit_transform(embeddings)

    clustered = cluster_ids != -1
    if topic:
        chosen = np.array([r["topic_label"] == topic for r in rows])
    else:
        chosen = clustered

    fig, ax = plt.subplots(figsize=(13, 10))
    ax.scatter(*coords[~clustered].T, s=6, color=NOISE, label="unclustered")
    ax.scatter(*coords[clustered & ~chosen].T, s=10, color=OTHER, label="other clusters")
    ax.scatter(*coords[chosen].T, s=16, color=HIGHLIGHT,
               label=f"{topic} clusters" if topic else "in a cluster",
               edgecolors="white", linewidths=0.4)

    # name the stories with the most outlets among the highlighted clusters
    stories = {}
    for row, point, on in zip(rows, coords, chosen, strict=True):
        if on:
            story = stories.setdefault(row["cluster_id"], {
                "title": row["title_summary"] or "", "points": [], "sources": set()})
            story["points"].append(point)
            story["sources"].add(row["source_name"])
    largest = sorted(stories.values(),
                     key=lambda s: (-len(s["sources"]), -len(s["points"])))[:LABELLED_STORIES]
    for story in largest:
        x, y = np.mean(story["points"], axis=0)
        ax.annotate("\n".join(textwrap.wrap(story["title"], 34)[:2]), (x, y),
                    xytext=(6, 6), textcoords="offset points", fontsize=7, color="#333333",
                    bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8})

    n_clusters = len(set(cluster_ids[clustered]))
    title = f"{len(rows)} articles, {n_clusters} clusters, last {window_days} days"
    if topic:
        title += f" - {len(stories)} labelled {topic}"
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    print(f"Saved visualization to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", help="highlight the clusters carrying this topic label")
    parser.add_argument("--days", type=int, default=CLUSTER_WINDOW_DAYS)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()
    visualize_clusters(topic=args.topic, window_days=args.days, output=args.output)
