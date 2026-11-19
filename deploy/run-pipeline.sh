#!/bin/sh
# The server's scheduler, in place of the laptop's Windows task. It brings the
# schema up to date, (re)creates the API's read-only account, then runs the
# pipeline every NEWSEYE_EVERY_HOURS hours (default 2). A run that outlasts the
# interval is followed by the next one a minute later; backend/pipeline.py's lock
# stops two runs from ever overlapping.
set -u

python -m backend.db.migrations || exit 1
python -m backend.db.api_role || exit 1

every=$(( ${NEWSEYE_EVERY_HOURS:-2} * 3600 ))
while true; do
    started=$(date +%s)
    python -m backend.pipeline --log /app/logs/pipeline.log
    took=$(( $(date +%s) - started ))
    wait=$(( every - took ))
    [ "$wait" -lt 60 ] && wait=60
    echo "pipeline: took ${took}s; next run in ${wait}s"
    sleep "$wait"
done
