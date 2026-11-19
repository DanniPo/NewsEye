#!/bin/sh
# A compressed pg_dump of the database once a day into ./backups on the server,
# keeping the newest NEWSEYE_BACKUPS_KEPT (default 7). deploy/README.md shows how
# to restore one, and how to copy them off the server.
set -u
kept="${NEWSEYE_BACKUPS_KEPT:-7}"

while true; do
    name="/backups/newseye-$(date -u +%Y-%m-%dT%H%MZ).dump"
    if pg_dump --format=custom --file="$name.part" && mv "$name.part" "$name"; then
        echo "backup: $name ($(du -h "$name" | cut -f1))"
    else
        echo "backup FAILED" >&2
        rm -f "$name.part"
    fi
    ls -1t /backups/newseye-*.dump 2>/dev/null | tail -n +"$((kept + 1))" | xargs -r rm -f
    sleep 86400
done
