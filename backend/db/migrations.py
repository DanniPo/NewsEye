"""Idempotent schema additions.

The base tables were created by hand, so this only carries the columns added
since. Every statement is safe to re-run: `python -m backend.db.migrations`.
"""
from backend.config import ANALYSIS_PENDING
from backend.db.connection import get_cursor

MIGRATIONS = [
    # two-stage analysis: the request handler writes a status, the worker advances it
    ("clusters.analysis_status", f"""
        ALTER TABLE clusters
            ADD COLUMN IF NOT EXISTS analysis_status text NOT NULL
            DEFAULT '{ANALYSIS_PENDING}'
    """),
    ("clusters.analysis_error", """
        ALTER TABLE clusters ADD COLUMN IF NOT EXISTS analysis_error text
    """),
    # the fast title-only summary lives alongside the deep one, never overwrites it
    ("clusters.coherence", """
        ALTER TABLE clusters ADD COLUMN IF NOT EXISTS coherence real
    """),
    ("cluster_analysis.title_summary", """
        ALTER TABLE cluster_analysis ADD COLUMN IF NOT EXISTS title_summary text
    """),
    ("cluster_analysis.title_summary_at", """
        ALTER TABLE cluster_analysis
            ADD COLUMN IF NOT EXISTS title_summary_at timestamptz
    """),
    # What the cluster is about, in its own headlines' words. Replaces
    # stance_subject: the phrase outlived the stance feature that needed it, and
    # the old name implied a measurement that no longer happens.
    ("cluster_analysis.subject", """
        ALTER TABLE cluster_analysis ADD COLUMN IF NOT EXISTS subject text
    """),
    ("cluster_analysis.sentiment_model", """
        ALTER TABLE cluster_analysis ADD COLUMN IF NOT EXISTS sentiment_model text
    """),
    ("cluster_analysis.framing", """
        ALTER TABLE cluster_analysis ADD COLUMN IF NOT EXISTS framing jsonb
    """),
    ("cluster_analysis.figure_digest", """
        ALTER TABLE cluster_analysis ADD COLUMN IF NOT EXISTS figure_digest jsonb
    """),
    ("cluster_analysis.cluster_id unique", """
        CREATE UNIQUE INDEX IF NOT EXISTS cluster_analysis_cluster_id_key
            ON cluster_analysis (cluster_id)
    """),
]


# Columns belonging to features that were removed after measurement. Dropping
# them is irreversible and takes the recorded results with it, so it is opt-in:
# the pipeline simply stops writing them, and they sit empty until asked for.
RETIRED = [
    # stance: classifier called "Appoints Kenyan Diplomat to Crucial New Role"
    # critical at 0.796, and disagreed with framing on the same outlet
    "stances", "stance_subject", "stance_model",
    # figure conflict adjudication: no true positive at 800 or 2,162 articles.
    # Superseded by figure_digest, which surfaces without ruling.
    "figure_conflicts",
    # abstractive deep summary: distilbart misspelled Kenyan names in 77/149
    "summary",
]


def migrate():
    with get_cursor() as cur:
        for name, statement in MIGRATIONS:
            cur.execute(statement)
            print(f"  ok  {name}")


def drop_retired():
    with get_cursor() as cur:
        for column in RETIRED:
            cur.execute(f"ALTER TABLE cluster_analysis DROP COLUMN IF EXISTS {column}")
            print(f"  dropped  cluster_analysis.{column}")


if __name__ == "__main__":
    import sys
    if "--drop-retired" in sys.argv:
        print("Dropping columns for removed features (irreversible)...")
        drop_retired()
    else:
        print("Applying schema additions...")
        migrate()
        print(f"\n{len(RETIRED)} retired columns still present and unwritten: "
              f"{', '.join(RETIRED)}")
        print("  drop them with: python -m backend.db.migrations --drop-retired")
    print("Done.")
