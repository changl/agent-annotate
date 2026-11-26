#!/bin/bash
# Stand-in for launchd com.agent-annotate.revive (StartInterval 60), sandbox env only.
DIR="$(cd "$(dirname "$0")" && pwd)"
for _ in $(seq 1 30); do
    "$DIR/aa" revive --quiet
    sleep 60
done
