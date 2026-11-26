#!/bin/bash
# Exit once the queued sandbox round leaves "pending" (or after 3 minutes).
DIR="$(cd "$(dirname "$0")" && pwd)"
for _ in $(seq 1 90); do
    if ! "$DIR/aa" py "$DIR/state.py" | grep -q "send .* pending"; then
        "$DIR/aa" py "$DIR/state.py"
        exit 0
    fi
    sleep 2
done
echo "still pending after 3 minutes"
"$DIR/aa" py "$DIR/state.py"
