#!/bin/bash
# Media Harvester.app launcher (copied to Contents/MacOS by build_mac_app.py).
# Finds Python, starts the bundled server in the background, and exits once it's up.
# The server opens the browser itself, and reopens it if the app is already running.

RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
LOG_DIR="$HOME/Library/Logs"
LOG="$LOG_DIR/Media Harvester.log"
mkdir -p "$LOG_DIR"
# Keep the log from growing forever
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG")" -gt 1000000 ]; then : > "$LOG"; fi

alert() {
    osascript -e "display alert \"$1\" message \"$2\" as critical buttons {\"$3\"} default button 1" >/dev/null 2>&1
}

# Finder gives apps a bare PATH, so check the usual Python locations directly
PY=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3; do
    if [ -x "$candidate" ] && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    alert "Media Harvester needs Python" "Install Python 3 from python.org, then open Media Harvester again." "Get Python"
    open "https://www.python.org/downloads/"
    exit 1
fi

if ! "$PY" -c 'import yt_dlp' 2>/dev/null; then
    osascript -e 'display notification "Getting set up. This only happens the first time." with title "Media Harvester"' >/dev/null 2>&1
fi

READY="$(mktemp -u "${TMPDIR:-/tmp}/mediaharvester-ready.XXXXXX")"
echo "--- $(date) ---" >> "$LOG"
nohup "$PY" -u "$RES/app/mediaharvester.py" --app --ready-file "$READY" >> "$LOG" 2>&1 &
PID=$!
disown

# Wait for the server to say it's ready (first run installs yt-dlp, so allow a few minutes)
for _ in $(seq 1 600); do
    if [ -e "$READY" ]; then
        rm -f "$READY"
        exit 0
    fi
    if ! kill -0 "$PID" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

rm -f "$READY"
if ! kill -0 "$PID" 2>/dev/null; then
    choice=$(osascript -e "display alert \"Media Harvester couldn't start\" message \"The details are in the log file.\" as critical buttons {\"Close\", \"Show Log\"} default button 2" 2>/dev/null)
    if [[ "$choice" == *"Show Log"* ]]; then
        open -R "$LOG"
    fi
    exit 1
fi
exit 0
