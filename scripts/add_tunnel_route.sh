#!/usr/bin/env bash
# add_tunnel_route.sh — register a Cloudflare tunnel ingress rule that
# points connelly.leadory.net/<slug>/* at a local sync_server port.
#
# Usage:
#   add_tunnel_route.sh --slug <slug> --service <origin-url> [--dry-run]
#   add_tunnel_route.sh --slug <slug> --port <n> [--dry-run]     # see WARNING
#
# Behavior:
#   - Reads cloudflare_api_key and connelly_cloudflared from
#     /Users/changlee/projects/connelly/claude/.env.local
#   - Decodes connelly_cloudflared (base64 JSON) for account_id; tunnel ID
#     is hardcoded to the Connelly tunnel.
#   - GETs current ingress, INSERTs a new rule for
#     connelly.leadory.net path /<slug>/.* → <service>
#     at position 0 (most-specific first). If a rule with the same
#     hostname + path already exists, REPLACES it in place — idempotent.
#   - Backs up the prior config to
#     ~/.claude/skills/annotate/cf-tunnel-config.backup-<UTC ISO>.json
#   - Prints the final public URL on success.
#
# Origin selection — exactly one of --service / --port is required:
#
#   --service <url>   The origin the connector dials. For an annotate page
#                     this is the `tailscale serve` endpoint fronting the
#                     sync server, e.g.
#                       --service https://macbook-pro.tail2b8ab9.ts.net:8456
#
#   --port <n>        WARNING: composes http://localhost:<n>. Verified on
#                     2026-07-31 to return 502 through this tunnel even
#                     though cloudflared runs on this same host — an
#                     identical ingress pair differed only in origin and
#                     only the tailscale one rendered. Kept as an explicit
#                     opt-in for a connector that CAN reach loopback; it has
#                     no default, so nothing composes it by accident.
#
#   --dry-run         Print the rule that would be written and exit without
#                     PUTting anything. Still takes a backup of nothing and
#                     performs no mutation.
#
# Exit codes:
#   0  success
#   2  bad arguments
#   3  env / token missing
#   4  Cloudflare API failure

set -euo pipefail

TUNNEL_ID="7075b8ac-3ebb-4ebd-8ac4-075d157d04d9"
ENV_FILE="/Users/changlee/projects/connelly/claude/.env.local"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME="connelly.leadory.net"

SLUG=""
PORT=""
SERVICE=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --slug)
            SLUG="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --service)
            SERVICE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
            exit 0
            ;;
        *)
            echo "ERROR: unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$SLUG" ]]; then
    echo "ERROR: --slug is required (e.g. --slug schema-v4-2)" >&2
    exit 2
fi

if [[ -n "$SERVICE" && -n "$PORT" ]]; then
    echo "ERROR: pass --service OR --port, not both" >&2
    exit 2
fi

if [[ -z "$SERVICE" && -z "$PORT" ]]; then
    echo "ERROR: an origin is required — pass --service <url> (recommended) or" >&2
    echo "       --port <n> to opt in to http://localhost:<n>, which 502s through" >&2
    echo "       this tunnel. See --help." >&2
    exit 2
fi

if [[ -z "$SERVICE" ]]; then
    if [[ ! "$PORT" =~ ^[0-9]+$ ]]; then
        echo "ERROR: --port must be a number (got: $PORT)" >&2
        exit 2
    fi
    SERVICE="http://localhost:${PORT}"
    echo "WARNING: using a loopback origin ($SERVICE). This tunnel returns 502" >&2
    echo "         for loopback origins; pass --service <tailscale-serve-url>." >&2
fi

if [[ ! "$SERVICE" =~ ^https?:// ]]; then
    echo "ERROR: --service must be an http:// or https:// URL (got: $SERVICE)" >&2
    exit 2
fi

# Strip any leading slash the user might pass and verify the slug is URL-safe
SLUG="${SLUG#/}"
if [[ ! "$SLUG" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: --slug must match [A-Za-z0-9._-]+ (got: $SLUG)" >&2
    exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file not found: $ENV_FILE" >&2
    exit 3
fi

# Decode account_id from connelly_cloudflared and read cloudflare_api_key.
# Token is intentionally not printed anywhere.
ACCOUNT_ID="$(
    python3 - "$ENV_FILE" <<'PY'
import base64, json, sys
vals = {}
with open(sys.argv[1]) as f:
    for line in f:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
t = vals.get("connelly_cloudflared", "")
if not t:
    sys.exit("ERROR: connelly_cloudflared missing")
pad = (4 - len(t) % 4) % 4
d = json.loads(base64.b64decode(t + "=" * pad).decode())
print(d["a"])
PY
)"

# shellcheck disable=SC2155
export CF_TOKEN="$(grep -E '^cloudflare_api_key=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
if [[ -z "$CF_TOKEN" ]]; then
    echo "ERROR: cloudflare_api_key missing from $ENV_FILE" >&2
    exit 3
fi

API_BASE="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations"
CURRENT_JSON="$(mktemp)"
trap 'rm -f "$CURRENT_JSON"' EXIT

curl -sf -H "Authorization: Bearer ${CF_TOKEN}" "$API_BASE" -o "$CURRENT_JSON" || {
    echo "ERROR: failed to GET tunnel config" >&2
    exit 4
}

if ! python3 -c "import json,sys;sys.exit(0 if json.load(open('$CURRENT_JSON'))['success'] else 1)"; then
    echo "ERROR: Cloudflare API returned success=false on GET" >&2
    exit 4
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${SCRIPT_DIR}/state/tunnel-backups/cf-tunnel-config.backup-${TIMESTAMP}.json"
mkdir -p "${SCRIPT_DIR}/state/tunnel-backups"
cp "$CURRENT_JSON" "$BACKUP_FILE"

PAYLOAD_FILE="$(mktemp)"
trap 'rm -f "$CURRENT_JSON" "$PAYLOAD_FILE"' EXIT

python3 - "$CURRENT_JSON" "$PAYLOAD_FILE" "$SLUG" "$SERVICE" "$HOSTNAME" <<'PY'
import json, sys
current_path, payload_path, slug, service, hostname = sys.argv[1:6]
current = json.load(open(current_path))
ingress = current["result"]["config"]["ingress"]
target_path = f"/{slug}/.*"
new_rule = {
    "path": target_path,
    "service": service,
    "hostname": hostname,
    "originRequest": {},
}
new_ingress = []
replaced = False
for rule in ingress:
    if rule.get("hostname") == hostname and rule.get("path") == target_path:
        new_ingress.append(new_rule)
        replaced = True
    else:
        new_ingress.append(rule)
if not replaced:
    new_ingress = [new_rule] + ingress
payload = {
    "config": {
        "ingress": new_ingress,
        "warp-routing": current["result"]["config"].get("warp-routing", {"enabled": False}),
    }
}
with open(payload_path, "w") as f:
    json.dump(payload, f)
print("replaced" if replaced else "inserted", file=sys.stderr)
PY

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "dry-run: would write ${HOSTNAME} /${SLUG}/.* -> ${SERVICE}"
    echo "backup: $BACKUP_FILE"
    python3 -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1]))['config']['ingress'][:3], indent=2))" "$PAYLOAD_FILE"
    exit 0
fi

RESP_FILE="$(mktemp)"
trap 'rm -f "$CURRENT_JSON" "$PAYLOAD_FILE" "$RESP_FILE"' EXIT

curl -sf -X PUT \
    -H "Authorization: Bearer ${CF_TOKEN}" \
    -H "Content-Type: application/json" \
    --data "@${PAYLOAD_FILE}" \
    "$API_BASE" \
    -o "$RESP_FILE" || {
    echo "ERROR: failed to PUT tunnel config" >&2
    exit 4
}

if ! python3 -c "import json,sys;d=json.load(open('$RESP_FILE'));sys.exit(0 if d['success'] else 1)"; then
    echo "ERROR: Cloudflare API returned success=false on PUT" >&2
    python3 -c "import json;print(json.load(open('$RESP_FILE'))['errors'])" >&2
    exit 4
fi

echo "backup: $BACKUP_FILE"
echo "URL:    https://${HOSTNAME}/${SLUG}/"
