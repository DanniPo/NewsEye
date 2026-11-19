# syntax=docker/dockerfile:1
# Newseye on a server. Two images, both built by docker-compose.yml at the
# repository root (see deploy/README.md):
#   app - the pipeline and the read-only API, with every model inside the image,
#         so a server never downloads one in the middle of a run;
#   web - Caddy serving the React pages and passing /api to the API, with HTTPS.

# ------------------------------------------------------------------ build ----
# Every requirement has a ready-built Linux wheel (hdbscan included), so no
# compiler is installed. The retries are for slow or dropping connections.
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_RETRIES=10 PIP_DEFAULT_TIMEOUT=120 \
    UV_HTTP_TIMEOUT=300 UV_HTTP_RETRIES=10 HF_HUB_DOWNLOAD_TIMEOUT=120 \
    HF_HOME=/models/hf TORCH_HOME=/models/torch UV_PYTHON_INSTALL_DIR=/opt/python

# The main environment. torch is the CPU build: a server has no graphics card,
# and the CUDA build is several gigabytes larger. requirements.txt pins the same
# version, which the CPU build satisfies.
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install torch==2.12.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && python -m spacy download en_core_web_sm

# NewsSentiment (targeted tone) needs Python 3.11 and torch < 2.1, so it gets its
# own environment, as on the laptop (eval/framing/README.md).
RUN pip install uv \
    && uv python install 3.11 \
    && uv venv --python 3.11 /opt/newsmtsc \
    && uv pip install --python /opt/newsmtsc/bin/python \
         --index-url https://download.pytorch.org/whl/cpu torch==2.0.1 \
    && uv pip install --python /opt/newsmtsc/bin/python NewsSentiment==1.2.28 "numpy<2"

# The models, fetched once at build time. The names are those in backend/config.py
# (EMBEDDING_MODEL, ZERO_SHOT_MODEL, SENTIMENT_MODEL); the app stage loads each
# one offline, so a name that no longer matches fails the build, not a run.
RUN python - <<'PY'
import time
from huggingface_hub import snapshot_download
skip = ["*.h5", "*.msgpack", "*.onnx", "onnx/*", "openvino/*", "*.ot", "coreml/*",
        "flax_model*", "tf_model*", "rust_model*"]
for repo in ("sentence-transformers/all-MiniLM-L6-v2",
             "MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33",
             "cardiffnlp/twitter-roberta-base-sentiment-latest"):
    for attempt in range(1, 6):   # a partial download resumes on the next attempt
        try:
            snapshot_download(repo, ignore_patterns=skip)
            break
        except Exception as exc:
            if attempt == 5:
                raise
            print(f"{repo}: {exc}; retrying", flush=True)
            time.sleep(10 * attempt)
PY
# NewsSentiment loads spaCy's English model in its own environment
RUN uv pip install --python /opt/newsmtsc/bin/python pip \
    && /opt/newsmtsc/bin/python -m spacy download en_core_web_sm
# GRU-TSC's weights (584 MB), in a step of their own so a rebuild reuses them
RUN for attempt in 1 2 3 4 5; do /opt/newsmtsc/bin/python -m NewsSentiment download && break; \
        [ "$attempt" = 5 ] && exit 1; sleep 15; done
# one score, which fetches what the model is built on and proves the worker runs
RUN /opt/newsmtsc/bin/python -c "from NewsSentiment import TargetSentimentClassifier as T; \
print(T().infer_from_text('Residents praised ', 'the governor', ' for the new road.')[0])"

# -------------------------------------------------------------------- app ----
FROM python:3.13-slim AS app
RUN useradd --create-home --uid 1000 newseye
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/python /opt/python
COPY --from=build /opt/newsmtsc /opt/newsmtsc
COPY --from=build --chown=1000:1000 /models /models
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 \
    HF_HOME=/models/hf TORCH_HOME=/models/torch HF_HUB_OFFLINE=1 \
    NEWSMTSC_PYTHON=/opt/newsmtsc/bin/python \
    TARGETED_CACHE=/data/targeted_scores.jsonl
WORKDIR /app
COPY backend backend
COPY deploy/run-pipeline.sh deploy/run-pipeline.sh
RUN mkdir -p /app/logs /data && chown newseye /app/logs /data
USER newseye
# every model loads from the image, offline: a failure here is a build failure
RUN python -c "from backend.nlp import embeddings, classification, nli; nli._load(); \
from backend.analysis.framing import get_sentiment; get_sentiment(); \
from backend.analysis.claims import get_nlp; get_nlp(); print('models load offline')"

# -------------------------------------------------------------------- web ----
FROM node:22-slim AS web-build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2 AS web
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/access-private.caddy deploy/access-public.caddy /etc/caddy/
COPY --from=web-build /web/dist /srv
