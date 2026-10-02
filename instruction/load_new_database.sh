#!/bin/bash
# Load a new TFBSpedia dump over the existing databases.
#
#   bash instruction/load_new_database.sh mouse
#   bash instruction/load_new_database.sh human
#
# Run one species at a time and let the checks pass before starting the next.
#
# DESTRUCTIVE: this drops the existing database before loading. The old dumps
# are kept compressed alongside the new archive, so a bad load can be undone by
# re-loading those, but that takes hours -- do not start without the disk space
# the pre-flight check asks for.
#
# Three things the dump does NOT bring with it, all handled below:
#   1. Django's own tables (django_*, auth_*, home_userprofile) live in whichever
#      database core/settings.py names as the "default" alias -- that is the
#      mouse database.  Reloading mouse drops them; `manage.py migrate` puts them
#      back.  Any logged-in sessions are lost, which for this site is harmless.
#   2. The two indexes the CSV downloads rely on.  Without them a download of a
#      large TF scans a 200M+ row table and the reverse proxy times out -- the
#      original "502 Proxy Error".
#   3. The pre-computed home page statistics, which are read from JSON files.

set -euo pipefail

SPECIES="${1:-}"
if [[ "$SPECIES" != "human" && "$SPECIES" != "mouse" ]]; then
    echo "usage: $0 {human|mouse}" >&2
    exit 2
fi

SQL_DIR="/Users/shitingli/Documents/temp_usage/TFBS_sql_files"
ARCHIVE="$SQL_DIR/TFBS_sql_files_v2.tar.gz"
MEMBER="${SPECIES}_TFBS_v2.sql"
DB="tfbspedia_${SPECIES}"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT/TFBS_djange/bin/python"

# Space the loaded database is expected to need.  Projected from the measured
# v2 mouse load (3.86 GB dump -> 15.4 GB database, 3.98x) scaled by each
# species' own v1 ratio: human's data is dominated by very large link tables
# that store more compactly, so it loads at a lower ratio than mouse.
# Override if you have a better number:  NEED_GB=170 bash load_new_database.sh human
case "$SPECIES" in
    human) NEED_GB="${NEED_GB:-145}" ;;
    mouse) NEED_GB="${NEED_GB:-18}"  ;;
esac
MARGIN_GB=8   # WAL, sort files and index builds all need room beyond the tables

echo "=== pre-flight ==="
[[ -f "$ARCHIVE" ]] || { echo "  archive not found: $ARCHIVE" >&2; exit 1; }

AVAIL_GB=$(df -g "$HOME" | tail -1 | awk '{print $4}')
# The existing database is dropped before the load starts, so its space is
# returned to the filesystem and counts towards what this load can use.
DROP_GB=$(psql -U postgres -tAc \
    "SELECT coalesce(round(pg_database_size('$DB')/1024.0^3), 0)" 2>/dev/null || echo 0)
DROP_GB=${DROP_GB:-0}
USABLE_GB=$(( AVAIL_GB + DROP_GB ))

echo "  free now .................. ${AVAIL_GB} GB"
echo "  released by dropping $DB .. ${DROP_GB} GB"
echo "  usable for the load ....... ${USABLE_GB} GB"
echo "  projected need ............ ${NEED_GB} GB (+${MARGIN_GB} GB margin)"

if (( USABLE_GB < NEED_GB + MARGIN_GB )); then
    echo >&2
    echo "  NOT ENOUGH SPACE: short by $(( NEED_GB + MARGIN_GB - USABLE_GB )) GB." >&2
    echo "  A load that runs out of disk leaves a half-populated database." >&2
    echo >&2
    echo "  Space you can reclaim without losing anything:" >&2
    for f in "$SQL_DIR"/*_TFBS_v2.sql; do
        [[ -e "$f" ]] || continue
        echo "    $(du -h "$f" | cut -f1)  $f" >&2
        echo "        (already loaded; still inside the archive)" >&2
    done
    for f in "$SQL_DIR"/*_TFBS_final.sql.gz; do
        [[ -e "$f" ]] || continue
        echo "    $(du -h "$f" | cut -f1)  $f" >&2
        echo "        (previous version's backup - keep until you trust the new data)" >&2
    done
    exit 1
fi
echo "  ok"

echo "=== stopping anything holding a connection ==="
pkill -f "manage.py runserver" 2>/dev/null || true
pkill -f "gunicorn core.wsgi" 2>/dev/null || true
sleep 2

echo "=== dropping and recreating $DB ==="
psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS $DB;"
psql -U postgres -d postgres -c "CREATE DATABASE $DB;"

echo "=== loading $MEMBER ==="
date
# ON_ERROR_STOP so a failure aborts here rather than leaving a partial load that
# looks like it worked.
if [[ -f "$SQL_DIR/$MEMBER" ]]; then
    # Already extracted: skip a full pass over the archive.  Members are stored
    # in one gzip stream, so reaching the mouse dump means decompressing the
    # 40 GB human one first.
    echo "  using already-extracted $SQL_DIR/$MEMBER"
    psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 -q -f "$SQL_DIR/$MEMBER"
else
    echo "  streaming from the archive (not written to disk)"
    tar -xzOf "$ARCHIVE" "$MEMBER" | psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 -q
fi
date
psql -U postgres -tAc "SELECT 'loaded: ' || pg_size_pretty(pg_database_size('$DB'));"

if [[ "$SPECIES" == "mouse" ]]; then
    echo "=== restoring Django's tables (mouse is the 'default' alias) ==="
    (cd "$PROJECT" && "$PYTHON" manage.py migrate)
fi

echo "=== rebuilding the download indexes ==="
psql -U postgres -d "$DB" -f "$PROJECT/instruction/sql_index_for_downloads.sql"

echo "=== updating planner statistics ==="
psql -U postgres -d "$DB" -c "ANALYZE;"

echo "=== compatibility checks ==="
(cd "$PROJECT" && "$PYTHON" instruction/check_database_compatibility.py "$SPECIES")

echo "=== refreshing the home page statistics ==="
(cd "$PROJECT" && "$PYTHON" instruction/make_database_stats.py "$SPECIES")

echo
echo "$SPECIES done. Restart the site to pick up the refreshed statistics:"
echo "  cd $PROJECT && $PYTHON manage.py runserver 8000"
