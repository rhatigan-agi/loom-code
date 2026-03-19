#!/usr/bin/env bash
# loom-code session timeout check — wired as a Stop hook in ~/.claude/settings.json.
# Fires after each Claude turn completes. Checks for long-running open sessions
# and emits a reminder to call loom_session_end before the conversation ends.
# Always exits 0 — this hook is advisory only, never blocks.

LOOM_HOME="${LOOM_HOME:-$HOME/.loom-code}"
ACTIVE_DIR="$LOOM_HOME/.active_sessions"
THRESHOLD_MIN=15

[ -d "$ACTIVE_DIR" ] || exit 0

NOW=$(date +%s)
REMINDED=false

for sentinel in "$ACTIVE_DIR"/*; do
    [ -f "$sentinel" ] || continue

    # Get sentinel creation time (mtime as proxy)
    if [[ "$(uname)" == "Darwin" ]]; then
        CREATED=$(stat -f "%m" "$sentinel" 2>/dev/null || echo "$NOW")
    else
        CREATED=$(stat -c "%Y" "$sentinel" 2>/dev/null || echo "$NOW")
    fi

    AGE_MIN=$(( (NOW - CREATED) / 60 ))

    if [ "$AGE_MIN" -ge "$THRESHOLD_MIN" ]; then
        PROJECT=$(basename "$sentinel")
        echo "loom-code: session '${PROJECT}' has been open for ${AGE_MIN}m. If work is complete or the conversation is winding down, call loom_session_end() now — do not wait for the user to say goodbye. Do NOT use loom_remember() as a substitute; it does not write a session record. Users may also run /wrap to trigger this explicitly."
        REMINDED=true
    fi
done

exit 0
