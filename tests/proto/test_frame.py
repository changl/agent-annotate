"""The frame's data: this page's waiting count and every project's read-only Home counts."""

import json
import os
import time
from pathlib import Path

from agent_annotate.proto_data import frame


def _page(d, waiting=0, versions=0):
    d.mkdir(parents=True)
    items = [{"id": f"q{i}", "author": "agent:x", "text": "Pick one?", "status": "open", "version": "v1",
              "decision_request": {"prompt": "Pick one?", "options": [{"id": "a", "label": "A"}]}} for i in range(waiting)]
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"a": items}, "archived": {}}))
    (d / "current.meta.json").write_text(json.dumps({"name": d.name, "current": "v1"}))
    (d / "versions").mkdir()
    for i in range(versions):
        (d / "versions" / f"v{i}.html").write_text("x")
    return d


def test_home_counts_group_pages_by_project_and_this_page_comes_first(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    _page(root / "rebex" / "reviews" / "one", waiting=2, versions=3)
    _page(root / "rebex" / "reviews" / "two", waiting=1, versions=1)
    _page(root / "leadory" / "reviews" / "plan")
    (root / "leadory" / "reviews" / "not-a-page").mkdir()
    old = root / "leadory" / "reviews" / "plan" / "versions" / "v0.html"
    old.write_text("x")
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    this = _page(tmp_path / "copy", waiting=3, versions=2)
    monkeypatch.setenv("ANNOTATE_PROTO_PROJECTS_ROOT", str(root))

    data = frame.build(this)

    assert data["waiting"] == 3
    keys = [p["key"] for p in data["projects"]]
    assert keys[0] == "this" and data["projects"][0]["this"] is True
    rebex = next(p for p in data["projects"] if p["key"] == "rebex")
    assert (rebex["name"], rebex["pages"], rebex["waiting"], sum(rebex["vday"])) == ("Rebex", 2, 3, 4)
    leadory = next(p for p in data["projects"] if p["key"] == "leadory")
    assert leadory["pages"] == 1 and sum(leadory["vday"]) == 0 and leadory["lastAgoH"] > 24 * 30
    json.dumps(data)  # the page gets it as JSON


def test_project_code_owner_and_last_send(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    rebex = _page(root / "rebex" / "reviews" / "one")
    meta = json.loads((rebex / "current.meta.json").read_text())
    meta["owner"] = {"owner_agent": "claude", "claimed_at": "2026-11-20T08:00:00Z", "target": {"pid": os.getpid()}}
    (rebex / "current.meta.json").write_text(json.dumps(meta))
    fld = _page(root / "fastlane-drive" / "reviews" / "page")
    meta = json.loads((fld / "current.meta.json").read_text())
    meta["owner"] = {"owner_agent": "codex", "claimed_at": "2026-11-19T08:00:00Z", "target": {"pid": 999999999}}
    (fld / "current.meta.json").write_text(json.dumps(meta))
    this = _page(tmp_path / "copy")
    (this / "project.json").write_text(json.dumps({"board": {"project": "fastlane-drive"}}))
    (this / "rounds.ndjson").write_text('{"ts": "2026-11-20T09:00:00Z", "delivery": "acknowledged", "answers": [1, 2]}\nnot json\n')
    monkeypatch.setenv("ANNOTATE_PROTO_PROJECTS_ROOT", str(root))
    frame._cache.clear()

    data = frame.build(this)

    by = {p["key"]: p for p in data["projects"]}
    assert by["rebex"]["code"] == "rebex" and "fastlane-drive" not in by  # the copy is FastLane Drive's one row
    assert by["rebex"]["owner"] == {"agent": "claude", "at": "2026-11-20T08:00:00Z", "alive": True}
    # a copy has no owner of its own: its project's session stands in, so Settings can name where a Send goes
    assert by["this"]["code"] == "fld" and by["this"]["owner"]["agent"] == "codex" and by["this"]["owner"]["alive"] is False
    assert data["lastSend"] == {"ts": "2026-11-20T09:00:00Z", "delivery": "acknowledged", "n": 2}


def _proto(d, **meta):
    _page(d)
    m = json.loads((d / "current.meta.json").read_text())
    m.update(ui="proto", **meta)
    (d / "current.meta.json").write_text(json.dumps(m))
    return d


def test_copies_stand_in_for_their_projects_one_row_each(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    src = _page(root / "rebex" / "reviews" / "rebex", waiting=1)
    _page(root / "fastlane-drive" / "reviews" / "page")
    _page(root / "leadory" / "reviews" / "plan")
    this = _proto(tmp_path / "reviews" / "fld-proto")
    (this / "project.json").write_text(json.dumps({"board": {"project": "fastlane-drive"}}))
    # copied today, published two days ago: the meta's history dates it, not the copy's file times
    two_days = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 2 * 86400))
    _proto(tmp_path / "reviews" / "proto-rebex", name="Rebex", proto_copy_of="rebex", proto_source=str(src), history=[{"version": "v1", "ts": two_days}])
    _proto(tmp_path / "reviews" / "misnamed", name="X", proto_copy_of="leadory")  # serve_other could never find it
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "s.json").write_text(json.dumps({"slugs": {"r": {"slug_dir": str(src), "public_url": "https://host.example/annotate/reviews/rebex/#review=SECRET"}}}))
    monkeypatch.setenv("ANNOTATE_PROTO_PROJECTS_ROOT", str(root))
    monkeypatch.setenv("ANNOTATE_PROTO_REGISTRY", str(reg))
    frame._cache.clear()

    data = frame.build(this)

    codes = [p["code"] for p in data["projects"] if p["code"] != "other"]
    assert len(codes) == len(set(codes)), codes  # one FastLane Drive row, one Rebex row (#2, #11)
    by = {p["key"]: p for p in data["projects"]}
    assert "fastlane-drive" not in by and by["this"]["code"] == "fld" and by["this"]["href"] == ""
    rebex = by["rebex"]
    assert rebex["href"] == "proto/p/rebex/" and rebex["name"] == "Rebex"
    assert rebex["url"] == "https://host.example/annotate/reviews/rebex/"  # its real page, never its key
    assert rebex["vday"][frame.DAYS - 3] == 1 and sum(rebex["vday"]) == 1
    assert "href" not in by["leadory"] and "SECRET" not in json.dumps(data)  # a project without a copy keeps its summary


def test_serve_other_reads_the_copy_and_nothing_writes_to_it(tmp_path):
    import http.client
    import threading
    from agent_annotate.sync_server import ReviewHTTPServer, make_handler

    reviews = tmp_path / "reviews"
    this = _proto(reviews / "fld-proto")
    copy = _proto(reviews / "proto-rebex", name="Rebex", proto_copy_of="rebex")
    _proto(reviews / "proto-bare", name="Bare")  # no proto_copy_of: not a served copy
    for d in (this, copy):
        (d / "current.html").write_text("<html><body>x</body></html>")
    web = Path(frame.__file__).resolve().parents[1] / "web"
    handler = make_handler(this, skill_dir=web, public_base_path="/review", slug="fld-proto")
    # published behind tailscale serve: only this page's slug has a publish record
    handler._published_proxy_origins = lambda self: {("https", "page.example.ts.net", 443)} if self.slug == "fld-proto" else set()
    httpd = ReviewHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def call(method, path, **headers):
        c = http.client.HTTPConnection(*httpd.server_address, timeout=5)
        c.request(method, path, body=b"{}" if method != "GET" else None, headers={"Content-Type": "application/json", **headers})
        r = c.getresponse()
        out = (r.status, r.getheader("Location"), r.read())
        c.close()
        return out

    try:
        status, _, body = call("GET", "/review/proto/p/rebex/current.meta.json")
        assert status == 200 and json.loads(body)["name"] == "Rebex"
        assert json.loads(call("GET", "/review/current.meta.json")[2])["name"] == "fld-proto"  # this page is untouched by the swap
        # through the proxy the copy is trusted on this page's published origin (it has no publish record of its own)
        tailnet = {"Host": "page.example.ts.net", "Tailscale-User-Login": "member@example.com"}
        status, _, body = call("GET", "/review/proto/p/rebex/current.meta.json", **tailnet)
        assert status == 200 and json.loads(body)["name"] == "Rebex"
        assert call("GET", "/review/proto/p/rebex/current.meta.json", Host="other.example.ts.net")[0] == 403
        assert call("GET", "/review/proto/p/rebex")[:2] == (308, "/review/proto/p/rebex/")
        assert call("GET", "/review/proto/p/nope/")[0] == 404
        assert call("GET", "/review/proto/p/bare/")[0] == 404
        before = (copy / "comments.json").read_text()
        for method in ("POST", "PUT", "DELETE"):
            assert call(method, "/review/proto/p/rebex/api/comments")[0] in (404, 405), method
        assert (copy / "comments.json").read_text() == before
    finally:
        httpd.shutdown()
        httpd.server_close()


# The broken frame items are browser behaviour; these pin the code that fixes each, so a later edit cannot drop it quietly.
WEB = Path(frame.__file__).resolve().parents[1] / "web" / "proto"


def _src(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_broken_items_keep_their_fixes():
    js, css, tokens, shell = _src("frame.js"), _src("frame.css"), _src("tokens.css"), _src("shell.html")
    # 1 another project opens with its six tabs, from Home and the project menu
    assert "data-proj=" in js and "`project/${d.proj}/questions`" in js and "function drawOther" in js
    # 2 a Home read that finishes after he left never draws over the tab
    home = js[js.index("async function drawHome"):js.index("function drawOther")]
    assert home.count("if (!S.home) return;") == 1 and "if (S.home && S.run) drawHome()" in home
    # 3 the review document follows Text size
    assert ".p-main{--aa-text:var(--fs,1)}" in tokens
    # 4 unsent answers stay in memory with the switch off, and old ones are dropped
    assert "DRAFT.test(k) && !remember('drafts')" in js and "if (!remember('drafts')) dropStoredDrafts();" in js
    # 5 folded sections are saved and restored with the switch on
    assert "addEventListener('toggle', saveFold, true)" in js and "restoreFolds(main)" in js
    # 6 a reload with Open tab off starts on Questions
    assert "nav.type === 'reload' && !remember('tab')" in js
    # 7 F and A from any tab open Questions and hand the key over; Esc closes an area's dialog
    assert "if ((k !== 'f' && k !== 'a') || onQuestions()) return;" in js and "new KeyboardEvent('keydown'" in js
    assert "[data-sendclose]" in js
    # 8 sign out shows the sign-in screen
    assert "function signOut" in js and "body.p-gated" in css
    # the Running fixer's stale render: each render draws into its own box
    assert "view.isConnected" in js and ".p-view{display:contents}" in css
    # 17 three skip links
    assert shell.count('class="skip"') == 3


def test_second_audit_fixes_stay():
    js, css = _src("frame.js"), _src("frame.css")
    # 1 a project with a prototype page of its own opens it; any other shows the dimmed empty state with its own page's link
    assert "location.replace(ROOT + S.other.href" in js and '<p class="mut dim">Nothing yet:' in js
    # 3 the unsaved inline note is a draft like the rest
    assert "q:newnote" in js[js.index("const DRAFT"):js.index("const GLOBAL")]
    # 4 Questions' own section folds are remembered and pressed back once
    assert "document.addEventListener('click', saveSecFold, true)" in js and "button[data-sfold]" in js[js.index("function restoreFolds"):js.index("function saveSecFold")]
    # 5 Open tab off: another project's tab returns to Questions on reload too
    assert "`#project/${anchor}/questions`" in js
    # 6, 7 jumps and skips land clear of the pinned frame and of a tab's own pinned bar
    assert js.count("scrollClear(") >= 3 and "html{scroll-padding-top:98px}" in css
    # 7 the document skip leaves Cards only, and never lands on a card's evidence
    assert "[data-view=\"doc\"]" in js and "'.aa.qdoc'" in js
    # 8 up to 900 the frame folds into its menu, and areas' pinned bars sit under its 44 px header
    assert "matchMedia('(max-width: 900px)')" in js and "@media (max-width:900px){" in css and "#p-main .qbar,#p-main .ajump{top:44px}" in css
    # 9 another project's scheduled jobs, by their Windmill folder
    assert "const jobsOf = code =>" in js
    # 10 no desk width hides the last Send
    assert "sentchip" not in css
    # 12 the overview opens on hover and focus; the phone keeps a failing job's red mark
    assert ".hov:hover>.hpop,.hov:focus-within>.hpop{display:block}" in css and ".wdots .wsep+.wd.jd{display:inline-grid}" in css
    # 13 History's arrows are listed and work
    assert "['← →', 'older or newer version, while one is open in History']" in js and "if (historyKey(e)) return;" in js
    # RR1 a read-only copy shows its own (simulated) Send in the header, never "Read-only copy"
    assert "const sendable = () => !!sendP;" in js and "roChip" not in js and "${beadsCtl()}${sendBtn('hide-ph')}" in js
    # fix3: the phone toast takes the screen's width (not half of it), wraps its links whole and sits above the floating Send
    assert ".p-toastwrap{position:fixed;left:12px;right:12px;bottom:18px;width:fit-content;margin:0 auto" in css
    assert "gap:12px;row-gap:4px" in css and "text-decoration:underline;white-space:nowrap" in css and ".p-toastwrap{bottom:82px}" in css


def test_fourth_check_frame_fixes_stay():
    js, css, q, run, links = (_src(n) for n in ("frame.js", "frame.css", "questions.js", "running.js", "links.js"))
    # frame 1: the document skip waits for the loaded text, after Questions has put back its old scroll
    assert "find(x => vis(x) && x.childElementCount)" in js
    # frame 2: People opens the sample denial screen, with a way back
    assert "data-denied>See what someone without access sees" in js and "data-signin=\"back\">Back to the page" in js
    # frame 3: the phone menu carries the last Send
    assert "beadsCtl(true) + lastSendChip('')" in js
    # frame 5: zero waiting still reads "0 waiting", never "N later"
    assert "text: `${n} waiting`, tone: n ? 'red' : 'green'" in q and " later`, title" not in q
    # frame 6: Owner keeps its own row on the phone, unwrapped
    assert '<span class="roleseg"><span class="ri8 small"' in js and ".prow .roleseg{grid-column:2/4" in css and ".roleseg .ri8{white-space:nowrap}" in css
    # running 3: a role button inside the Add form never submits it
    assert '<button type="button" ${attr}=' in links
    # questions 04: a task link opens Running's full panel beside Questions, not an inline preview
    assert "P.taskPanel(host, ctx, id" in q and "qpeek" not in q and "P.taskPanel = async" in run and "tabNow === 'side' ? panel()" in run
