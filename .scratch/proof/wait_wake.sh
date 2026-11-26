#!/bin/bash
# Exit once a resume marker for the given terminal handle leaves "pending" (or after 3 minutes).
DIR="$(cd "$(dirname "$0")" && pwd)"
for _ in $(seq 1 90); do
    if "$DIR/aa" py "$DIR/state.py" | grep "resume .* $1" | grep -qv " pending "; then
        "$DIR/aa" py "$DIR/state.py"
        exit 0
    fi
    sleep 2
done
echo "no wake-up after 3 minutes"
"$DIR/aa" py "$DIR/state.py"
