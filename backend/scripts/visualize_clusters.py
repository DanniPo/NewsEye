import numpy as np
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from backend.db.connection import get_cursor

OUTPUT_PATH = "cluster_visualization.png"

def parse_embedding(value):
    if isinstance(value, str):
        return [float(x) for x in value.strip("[]").split(",")]
    return value

def visualize_clusters():
    with get_cursor() as cur:
        cur.execute("""
            SELECT a.id, a.embedding, cm.cluster_id, c.topic_label
            FROM articles a
            LEFT JOIN cluster_members cm ON cm.article_id = a.id
            LEFT JOIN clusters c ON c.id = cm.cluster_id
            WHERE a.embedding IS NOT NULL
        """)
        rows = cur.fetchall()

    embeddings = np.array([parse_embedding(r["embedding"]) for r in rows], dtype=float)
    cluster_ids = [r["cluster_id"] if r["cluster_id"] is not None else -1 for r in rows]
    labels = [r["topic_label"] for r in rows]

    coords = PCA(n_components=2).fit_transform(embeddings)

    plt.figure(figsize=(12, 9))
    noise_mask = np.array(cluster_ids) == -1
    plt.scatter(coords[noise_mask, 0], coords[noise_mask, 1],
                c="lightgray", s=12, label="noise", alpha=0.5)

    unique_clusters = sorted(set(cid for cid in cluster_ids if cid != -1))
    cmap = plt.get_cmap("tab20", max(len(unique_clusters), 1))
    for i, cid in enumerate(unique_clusters):
        mask = np.array(cluster_ids) == cid
        topic = next((labels[j] for j in range(len(labels)) if cluster_ids[j] == cid), "?")
        plt.scatter(coords[mask, 0], coords[mask, 1],
                    color=cmap(i), s=25, label=f"{cid}:{topic}")

    plt.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5))
    plt.title("Article clusters (PCA projection of embeddings)")
    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, dpi=150)
    print(f"Saved visualization to {OUTPUT_PATH}")

if __name__ == "__main__":
    visualize_clusters()
