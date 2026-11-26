"""Reviewer flow against the sandbox server: agent asks a card, reviewer answers it and presses Send."""
import http.client
import json
import sys


def call(method, path, body=None, author="agent:proof"):
    conn = http.client.HTTPConnection("127.0.0.1", 18700, timeout=30)
    headers = {"X-Annotate-Agent": author} if author.startswith("agent:") else {
        "Host": "review.example.test", "Cf-Access-Authenticated-User-Email": author,
        "Cf-Access-Jwt-Assertion": "inert-proxy-validated-assertion"}
    payload = json.dumps(body).encode() if body is not None else None
    if payload:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    print(method, path, resp.status, data[:300].decode(errors="replace"))
    return json.loads(data)


label = sys.argv[1] if len(sys.argv) > 1 else "proof"
card = call("POST", "/api/comments", {
    "anchor_id": "s:a", "text": f"Ship {label}?", "decision_request": {
        "prompt": f"Ship {label}?", "context": "restart proof", "recommendation": "accept",
        "options": [{"id": "accept", "label": "Yes", "consequence": "ships"},
                    {"id": "reject", "label": "No", "consequence": "waits"}],
        "impact": "low", "blocking": True}})
call("POST", f"/api/comments/{card['id']}/decision", {"verdict": "accept"}, author="reviewer@example.test")
call("POST", "/api/rounds/submit", {}, author="reviewer@example.test")
