RSS_FEEDS = [
    {"name": "Kenya News", "rss_url": "https://www.kenyanews.go.ke/feed/"},
    {"name": "The Kenya Times", "rss_url": "https://thekenyatimes.com/feed/"},
    {"name": "Capital FM", "rss_url": "https://www.capitalfm.co.ke/news/feed/"},
    {"name": "KBC", "rss_url": "https://www.kbc.co.ke/feed/"},
    {"name": "Amref Newsroom", "rss_url": "https://newsroom.amref.org/feed/"},
    {"name": "Business Daily Africa", "rss_url": "https://www.businessdailyafrica.com/latestrss.rss"},
    {"name": "K24 Digital", "rss_url": "https://k24.digital/feed"},
    {"name": "The Sharp Daily", "rss_url": "https://thesharpdaily.com/feed/"},
    {"name": "Nairobi Wire", "rss_url": "https://nairobiwire.com/feed"},
    {"name": "The East African", "rss_url": "https://www.theeastafrican.co.ke/service/rss/tea/1289142/feed.rss"},
    {"name": "Nation Africa", "rss_url": "https://nation.africa/kenya/rss.xml"},
    {"name": "People Daily", "rss_url": "https://peopledaily.digital/feed"},
]
# How many items to take from each feed per run. At 5 the corpus reached only
# ~2 articles per outlet per day, so three outlets rarely covered the same event
# and only 7 of 126 clusters ended up with 3+ sources. Cross-source comparison is
# the entire product, and it is starved by thin ingestion, not by weak models.
# Dedupe makes re-reading the same items free, so this can be raised freely.
ARTICLES_PER_FEED = 25

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
ZERO_SHOT_MODEL = "MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33"
TOPIC_LABELS = [
    "Politics", "Business", "Economy", "Security", "Health",
    "Counties", "Sports", "Entertainment", "Technology",
    "International", "Weather", "Education", "Science"
]
FALLBACK_LABEL = "General"
HDBSCAN_MIN_CLUSTER_SIZE = 2
HDBSCAN_MIN_SAMPLES = 1
CLUSTER_WINDOW_DAYS = 7
MAX_CLUSTER_SHARE = 0.25
# mean pairwise cosine similarity inside a cluster. Below this the members are not
# one story: a 0.458 cluster paired "Hilarious Memes in Nairobi" with horticulture
# trade policy, and every downstream stage inherited the mess - the summariser
# invented a connecting narrative, the subject came out as bare "Nairobi", and
# framing compared entities across unrelated events.
CLUSTER_MIN_COHERENCE = 0.50
# below this zero-shot confidence an article's topic is recorded as FALLBACK_LABEL
TOPIC_CONFIDENCE_THRESHOLD = 0.75
SNIPPET_MAX_LENGTH = 150
# MiniLM truncates at 256 tokens, so more than ~1000 chars is wasted
EMBED_MAX_CHARS = 1000
# passive tier embeds snippets only so every article is represented the same way;
# full text is fetched on demand by the active tier instead
FETCH_FULL_TEXT = False

# --- active tier (on-demand deep analysis) ---
# scores each sentence that names an entity; three-class, so it can say neutral
SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
# What actually produces the cluster summaries a reader sees. They are not
# generated: representative_title() picks the member headline closest to the
# cluster centroid, so the only model involved is the embedding model used to
# measure that distance. This column previously named distilbart, crediting it
# with 309 summaries it never saw - exactly the provenance error the model
# versioning columns exist to prevent.
TITLE_SUMMARY_MODEL = f"extractive-medoid/{EMBEDDING_MODEL}"

CLAIM_ENTITY_TYPES = ("CARDINAL", "QUANTITY", "MONEY", "PERCENT", "DATE")
CLAIM_MIN_CHARS = 40
# how much surrounding text to keep with each claim. A figure alone is not
# evidence - the reader needs enough around it to judge whether two numbers are
# measuring the same thing. Bounded, because the active tier discards article
# bodies: this is a derived excerpt, not a stored copy.
CLAIM_CONTEXT_CHARS = 600
CLAIM_MAX_PER_ARTICLE = 8
ANALYSIS_MAX_ARTICLES = 12
# below this an extraction is navigation, not an article. Kept low because
# paywall stubs are caught by their own marker rather than by length - a 500
# floor was discarding real 300-500 character reports.
MIN_BODY_CHARS = 250
FETCH_CONCURRENCY = 3
FETCH_DELAY_SECONDS = 0.4

# two claims count as the same fact when their embeddings are at least this close
# (cosine distance). Drives the coverage table: which outlets carried each fact.
CLAIM_MATCH_MAX_DISTANCE = 0.4

# analysis_status values on clusters, driving the two-stage summary in the UI
ANALYSIS_PENDING = "pending"
ANALYSIS_PREVIEW_READY = "preview_ready"
ANALYSIS_DEEP_READY = "deep_ready"
ANALYSIS_FAILED = "failed"

# Terms so universal in this corpus that naming them tells a reader nothing.
# Every feed here is Kenyan, so "Kenya" appears in most articles of most
# clusters: it identifies the corpus, not the story. It caused two separate
# visible defects. As a subject head it recurred in 4 of 7 titles of the 2029
# athletics story and won the ranking, so the subject label came out as "Absa
# Bank Kenya" - the widest noun phrase ending in "Kenya" happened to be a
# sponsor's name. As a framing entity it accounted for 5 of 11 divergences,
# comparing outlets' sentiment toward their own country.
#
# This is the document-frequency argument that SUBJECT_DF_LIMIT already applies
# to figure subjects, hardcoded because it is a property of the feed list rather
# than of any one cluster. Change it if the feeds stop being Kenyan. Cities,
# institutions and people are deliberately absent: "Nairobi" framed at -0.25 by
# K24 against +0.60 by KBC is one of the sharpest findings in the corpus.
CORPUS_UNIVERSAL_TERMS = {"kenya", "kenyan", "kenyans", "kenya's", "kenyas"}

# --- entity framing (how differently sources describe the same thing) ---
# an entity must be mentioned by at least this many outlets before their
# descriptions of it can be compared at all
FRAMING_MIN_SOURCES = 2
# and mentioned this many times by an outlet before that outlet's score means
# anything - one sentence is an anecdote, not a frame
FRAMING_MIN_MENTIONS = 2
# the gap in signed sentiment (-1..1) at which two outlets are said to frame
# the same entity differently
FRAMING_DIVERGENCE = 0.35
