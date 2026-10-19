import os

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
# Two clusters whose mean embeddings sit within this cosine distance are shown
# together in search as strands of one larger story. They are never merged in
# the database: coverage compares outlets on one event, and folding the Dangote
# groundbreaking into the court order halting it would count every outlet that
# covered only one of them as having omitted the other. At 0.35 the pairs on a
# day's clusters were all genuine (Dangote, El Nino, the HIV pill); at 0.45 a
# death notice, a party launch, memes and a footballer came out as one group.
RELATED_STORY_MAX_DISTANCE = 0.35
# a re-clustered story keeps its id when it shares at least this share of the
# smaller of its old and new memberships (see match_clusters)
CLUSTER_CONTINUITY_SHARE = 0.5
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

# --- natural language inference ---
# The topic classifier's checkpoint is a two-label NLI model (entailment /
# not_entailment), used only to ask whether two versions of something say the
# same thing. backend/nlp/nli.py explains why it has no contradiction label, and
# why that is deliberate.
NLI_MODEL = ZERO_SHOT_MODEL
# P(entailment) at or above this counts as "implies"
NLI_ENTAILS = 0.5
# Check each coverage-table match with NLI. Similarity alone merged different
# facts in 17 of 30 hand-checked cross-outlet pairs; see analysis/consensus.py.
CLAIM_MATCH_NLI = True

# --- quotes (active tier) ---
# shorter "quotes" are scare quotes and nicknames: a 'modern' police force, "Wantam"
QUOTE_MIN_WORDS = 4
# kept per quote; the article itself is discarded, as with claims
QUOTE_MAX_CHARS = 400
# two quotes from one speaker in two outlets are the same remark at this
# embedding similarity; NLI then says how the versions relate
QUOTE_MATCH_SIMILARITY = 0.7

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

# How a mention is scored. "sentence": the tone of the whole sentence (RoBERTa),
# which reads "Ruto condemns the killings" as negative without it being negative
# about Ruto. "targeted": the writer's attitude toward that entity (NewsMTSC's
# GRU-TSC, Hamborg & Donnay 2021), falling back to sentence tone for anything it
# cannot score. Targeted since 16 Oct 2026: on NewsMTSC's human-labelled test sets
# it beat sentence tone by +0.150 F1m (rw, 95% CI +0.113 to +0.189) and +0.199
# (mt, +0.167 to +0.232), the rule fixed before the run (eval/framing/benchmark.md).
# The labelled Kenyan sample (eval/framing/report.md) confirms or reverts it;
# FRAMING_SENTIMENT=sentence in the environment switches back without a code change.
FRAMING_SENTIMENT = os.environ.get("FRAMING_SENTIMENT", "targeted")
# the neutral band for targeted scores (P(positive) - P(negative)), tuned on the
# NewsMTSC rw dev split; retune on the Kenyan dev split once it is labelled
FRAMING_TARGETED_THRESHOLD = 0.29
# NewsMTSC was trained on people only; add a type only where the report's
# "not PERSON" row supports it
TARGETED_ENT_TYPES = {"PERSON"}
# NewsSentiment needs Python 3.8-3.11, torch < 2.1 and transformers <= 4.24, so it
# runs in its own environment as a long-lived worker (backend/analysis/targeted.py)
NEWSMTSC_PYTHON = os.environ.get("NEWSMTSC_PYTHON") or os.path.join(
    os.path.expanduser("~"), ".venvs", "newsmtsc",
    "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
# Targeted scores already computed, keyed by text, offsets and model version. The
# model takes 1-2 s a mention on this laptop's CPU and ~0.26 s on its GPU, and
# headlines never change, so each mention is scored once. Outside the
# repository: it holds headline text.
TARGETED_CACHE = os.environ.get("TARGETED_CACHE") or os.path.join(
    os.path.expanduser("~"), ".cache", "newseye", "targeted_scores.jsonl")

# --- Kenyan entities (names, institutions, places) ---
# spaCy's small English model, named here so it is never a library default. It
# tagged Kenyan names and institutions correctly in 26% of headlines and 74% of
# snippet sentences: it was trained on American news and leans on capitals.
SPACY_MODEL = "en_core_web_sm"
# The list that fixes that for known names, loaded before spaCy's own entity
# model. Plain JSON so it can be read and corrected without touching code.
KENYAN_ENTITIES_PATH = os.path.join(os.path.dirname(__file__), "data", "kenya_entities.json")
# Titles that precede a person's name in Kenyan news. They catch names the list
# has never seen: "CS Mugaa", "MP Wandeto", "Governor Kahiga". 328 different
# surnames follow one of these somewhere in the corpus. Multi-word titles are
# written out in full; matching ignores case.
NAME_TITLES = (
    "president", "deputy president", "dp", "former president", "prime cs",
    "prime cabinet secretary", "cs", "cabinet secretary", "ps", "principal secretary",
    "governor", "deputy governor", "senator", "mp", "mca", "woman rep", "women rep",
    "speaker", "chief justice", "cj", "justice", "lady justice", "judge", "ig",
    "inspector general", "attorney general", "auditor general", "controller of budget",
    "commissioner", "ambassador", "dr", "prof", "professor", "hon", "rev", "bishop",
    "archbishop", "cardinal", "pastor", "imam", "sheikh",
    # roles written as titles: "IEBC Chairperson Erastus Ethekon"
    "chairperson", "chairman", "chairwoman", "chair", "ceo", "director",
    "director general", "secretary general", "spokesperson", "spokesman",
)

# --- portrayal (how each outlet presents a public figure) ---
# Verbs an outlet uses to report what someone said, grouped by what the choice
# conveys. The groups describe words, not outlets: "claims" distances the writer
# from the claim, "assures" lends it credit. Shown to readers alongside the verbs
# themselves; nothing is scored. Two-word entries are verb + particle.
REPORTING_VERBS = {
    # the held-out test (19 Oct) found "Kalonzo Musyoka has reaffirmed that..." read
    # as acting: reaffirm and its kin were missing
    "said": ("say", "tell", "state", "note", "add", "explain", "announce", "reveal",
             "respond", "reply", "react", "describe", "disclose", "confirm", "speak",
             "remark", "address", "write", "report", "affirm", "reaffirm", "reiterate",
             "stress", "emphasise", "emphasize", "recall", "acknowledge", "admit"),
    "claimed": ("claim", "allege", "insist", "maintain", "contend", "purport"),
    "promised or assured": ("assure", "reassure", "pledge", "promise", "vow"),
    "praised": ("hail", "laud", "praise", "commend", "congratulate", "thank", "applaud",
                "celebrate", "champion"),
    "criticised": ("slam", "blast", "criticise", "criticize", "castigate", "attack",
                   "accuse", "blame", "condemn", "decry", "dismiss", "rubbish",
                   "lash out", "hit back", "fire back", "hit out", "challenge",
                   "censure", "fault", "rebuke", "mock", "ridicule", "taunt",
                   "take aim", "take swipe", "take jibe", "take dig"),
    "denied or defended": ("deny", "defend", "refute", "reject", "dispute", "counter"),
    "urged or warned": ("urge", "call on", "call for", "appeal", "ask", "implore",
                        "plead", "warn", "caution", "direct", "order", "demand", "threaten"),
}
