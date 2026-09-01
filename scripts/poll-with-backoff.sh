#!/usr/bin/env bash
set -euo pipefail

POLL_SCRIPT="${POLL_SCRIPT:-$HOME/technocore-agent/poll-mailbox.sh}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-8}"
INITIAL_DELAY="${INITIAL_DELAY:-30}"
MAX_DELAY="${MAX_DELAY:-600}"

if [[ ! "$MAX_ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: MAX_ATTEMPTS must be a positive integer" >&2
    exit 2
fi

if [[ ! "$INITIAL_DELAY" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: INITIAL_DELAY must be a positive integer" >&2
    exit 2
fi

if [[ ! "$MAX_DELAY" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: MAX_DELAY must be a positive integer" >&2
    exit 2
fi

if [ "$INITIAL_DELAY" -gt "$MAX_DELAY" ]; then
    echo "ERROR: INITIAL_DELAY cannot exceed MAX_DELAY" >&2
    exit 2
fi

if [ ! -x "$POLL_SCRIPT" ]; then
    echo "ERROR: poller is missing or not executable: $POLL_SCRIPT" >&2
    exit 1
fi

DELAY="$INITIAL_DELAY"
ATTEMPT=1

while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do
    TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    echo "[$TIMESTAMP] mailbox poll attempt $ATTEMPT/$MAX_ATTEMPTS" >&2

    set +e
    "$POLL_SCRIPT"
    STATUS=$?
    set -e

    case "$STATUS" in
        0)
            # A valid batch was returned, or no new messages were available.
            # Processing and acknowledgement belong to the caller.
            exit 0
            ;;

        75)
            # Transient HTTP or service availability failure.
            if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
                echo "Retry limit reached; cursor remains unchanged" >&2
                exit 75
            fi

            JITTER=$((RANDOM % 16))
            WAIT_SECONDS=$((DELAY + JITTER))

            echo "Transient failure; retrying in $WAIT_SECONDS seconds" >&2
            sleep "$WAIT_SECONDS"

            if [ "$DELAY" -lt "$MAX_DELAY" ]; then
                DELAY=$((DELAY * 2))

                if [ "$DELAY" -gt "$MAX_DELAY" ]; then
                    DELAY="$MAX_DELAY"
                fi
            fi
            ;;

        3)
            echo "History gap detected; automatic retry stopped" >&2
            exit 3
            ;;

        4)
            echo "Mailbox generation changed; automatic retry stopped" >&2
            exit 4
            ;;

        76)
            echo "An unacknowledged batch is pending; automatic retry stopped" >&2
            exit 76
            ;;

        *)
            echo "Non-transient poll failure $STATUS; automatic retry stopped" >&2
            exit "$STATUS"
            ;;
    esac

    ATTEMPT=$((ATTEMPT + 1))
done

exit 75
