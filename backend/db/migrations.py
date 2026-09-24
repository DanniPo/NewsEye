"""Create and update the schema. Idempotent: safe to re-run at any time.

    python -m backend.db.migrations                  # create/update everything
    python -m backend.db.migrations --drop-retired   # remove dead columns

BASE_SCHEMA builds the database from nothing, so a fresh clone needs only an
empty database. It did not used to: the four tables were created by hand during
early development and only the later columns were recorded here, which meant the
repository could not reproduce its own schema.

MIGRATIONS carries everything added after those tables existed. The split is
kept rather than folded together because the ALTERs document when and why each
column appeared, which the CREATE TABLEs no longer show.
"""
from backend.config import ANALYSIS_PENDING, EMBEDDING_DIM
from backend.db.connection import get_cursor

BASE_SCHEMA = [
    # pgvector supplies the embedding column type and the HNSW index
    ("extension: vector", "CREATE EXTENSION IF NOT EXISTS vector"),

    # One row per article ever seen. Append-only: nothing in the pipeline
    # updates or deletes a row. Bodies are never stored - the active tier
    # fetches text transiently and discards it.
    ("table: articles", f"""
        CREATE TABLE IF NOT EXISTS articles (
            id              serial PRIMARY KEY,
            identifier      text NOT NULL UNIQUE,
            source_name     text NOT NULL,
            title           text NOT NULL,
            url             text NOT NULL,
            url_canon       text NOT NULL,
            published_utc   timestamptz NOT NULL,
            snippet         text,
            category        text,
            category_model  text,
            embedding       vector({EMBEDDING_DIM}),
            inserted_at_utc timestamptz NOT NULL DEFAULT now()
        )
    """),

    # Rebuilt from scratch on every clustering run (TRUNCATE ... RESTART
    # IDENTITY CASCADE in nlp/clustering.py), so ids are not stable across runs.
    ("table: clusters", f"""
        CREATE TABLE IF NOT EXISTS clusters (
            id              serial PRIMARY KEY,
            topic_label     text,
            article_count   integer,
            coherence       real,
            label_model     text,
            analysis_status text NOT NULL DEFAULT '{ANALYSIS_PENDING}',
            analysis_error  text,
            created_at      timestamptz DEFAULT now()
        )
    """),

    ("table: cluster_members", """
        CREATE TABLE IF NOT EXISTS cluster_members (
            id         serial PRIMARY KEY,
            cluster_id integer NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
            article_id integer NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            UNIQUE (cluster_id, article_id)
        )
    """),

    # Derived results only. The foreign key is what makes the clustering
    # TRUNCATE cascade to here, which is why the summarise stage must always
    # follow the cluster stage.
    ("table: cluster_analysis", """
        CREATE TABLE IF NOT EXISTS cluster_analysis (
            id               serial PRIMARY KEY,
            cluster_id       integer UNIQUE REFERENCES clusters(id) ON DELETE CASCADE,
            title_summary    text,
            title_summary_at timestamptz,
            subject          text,
            tone             text,
            tone_score       real,
            consensus        jsonb,
            framing          jsonb,
            figure_digest    jsonb,
            sources_used     integer,
            nli_model        text,
            summary_model    text,
            sentiment_model  text,
            analyzed_at      timestamptz DEFAULT now()
        )
    """),

    # Cosine because the embeddings are L2-normalised at write time.
    ("index: articles.embedding (hnsw)", """
        CREATE INDEX IF NOT EXISTS articles_embedding_idx
            ON articles USING hnsw (embedding vector_cosine_ops)
    """),
    # Postgres does not index foreign keys automatically, and every cluster
    # read joins through both of these.
    ("index: cluster_members.cluster_id", """
        CREATE INDEX IF NOT EXISTS cluster_members_cluster_id_idx
            ON cluster_members (cluster_id)
    """),
    ("index: cluster_members.article_id", """
        CREATE INDEX IF NOT EXISTS cluster_members_article_id_idx
            ON cluster_members (article_id)
    """),
    # clustering filters the 7-day window on published_utc; the due-check counts
    # rows by inserted_at_utc
    ("index: articles.published_utc", """
        CREATE INDEX IF NOT EXISTS articles_published_utc_idx
            ON articles (published_utc DESC)
    """),
    ("index: articles.inserted_at_utc", """
        CREATE INDEX IF NOT EXISTS articles_inserted_at_utc_idx
            ON articles (inserted_at_utc DESC)
    """),
]

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

# Early development left a second HNSW index on the same column under a
# generated name. Two identical indexes double the write cost of every insert
# and the memory the index occupies, for no read benefit.
CLEANUP = [
    ("drop duplicate embedding index", "DROP INDEX IF EXISTS articles_embedding_idx1"),
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
        for label, statement in BASE_SCHEMA + MIGRATIONS + CLEANUP:
            cur.execute(statement)
            print(f"  ok  {label}")


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
        print("Creating and updating schema...")
        migrate()
        print(f"\n{len(RETIRED)} retired columns still present and unwritten: "
              f"{', '.join(RETIRED)}")
        print("  drop them with: python -m backend.db.migrations --drop-retired")
    print("Done.")
