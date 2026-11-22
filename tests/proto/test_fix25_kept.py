"""Twenty-fifth check: the published-page reader keeps note anchors, attachment pictures and long code (r12 audit21
running 1, reference 1, 2 and 3)."""

from test_fix23_media import png
from test_fix24_kept import HTML

from agent_annotate.proto_data import links, reference


def test_blocks_take_the_published_pages_own_anchors():
    ids = []
    b = links.html_blocks(HTML, None, ids)
    assert len(ids) == len(b)
    got = dict(zip([x[1] if x[0] != "tbl" else "tbl" for x in b], ids))
    assert got["Intro."] == "s:kept:p1" and got["Below the picture."] == "s:kept:p2" and got["printf released\n  printf next"] == "s:kept:code1"
    # a table: its own, then each body row's own anchor; a row with none goes by its number in the table
    assert got["tbl"] == ["tbl:kept", "tbl:kept:row:first", "tbl:kept~r2"]
    assert len({x if isinstance(x, str) else x[0] for x in ids}) == len(ids)  # unique, so each line is its own note's place


def test_a_note_on_the_old_readers_line_number_lands_on_its_words():
    ids = []
    b = links.html_blocks(HTML, None, ids)
    was = links.old_lines(HTML, b, ids)
    # the twentieth check's reader: h1, h2, Intro., Below the picture., then each cell, then the code
    assert was["3"] == "s:kept:p2" and was["2"] == "s:kept:p1"
    assert was["5"] == "tbl:kept:row:first" and was["7"] == "tbl:kept~r2" and was["8"] == "s:kept:code1"
    w = {"admin-meeting": was}
    assert links.moved("doc:kept-admin-meeting~p~3", w) == "doc:kept-admin-meeting~p~s:kept:p2"
    assert links.moved("doc:kept-admin-meeting~p~99", w) == "doc:kept-admin-meeting"  # its words are gone: the whole document
    for same in ("doc:kept-admin-meeting~p~s:kept:p2", "doc:kept-load-test~p~0", "doc:kept-admin-meeting~2", None):
        assert links.moved(same, w) == same


def test_pictures_under_attachments_show_as_today(tmp_path):
    page = tmp_path / "page"
    (page / "attachments").mkdir(parents=True)
    (page / "attachments" / "x.png").write_bytes(png(4, 4))
    src = links._kept_src("usage-audit", page)
    b = links.html_blocks('<body><img src="attachments/x.png" alt="X" width="1440" height="760"><table><tr><td>a</td></tr>'
                          '<tr><td><img src="attachments/x.png" alt="Y"></td></tr></table></body>', src)
    assert b[0] == ["img", "proto/kept/usage-audit/attachments/x.png#wh=1440x760", "X", 1]
    assert b[1][4][1][0][0] == ["img", "proto/kept/usage-audit/attachments/x.png#wh=4x4", "Y", 2]
    assert links.kept_picture(page, "attachments/x.png") == page / "attachments" / "x.png"
    assert links.kept_picture(page, "attachments/../x.png") is None


def test_nothing_is_cut():
    code = "\n".join(f"echo line {i} {'x' * 40}" for i in range(450)) + "\nprintf complete"
    long = "word " * 400
    b = links.html_blocks(f"<body><pre>{code}</pre><p>{long}</p><p><img alt=\"{'a' * 500}\" src=\"x.png\"></p>"
                          + "".join(f"<p>line {i}</p>" for i in range(900)) + "</body>", reference._kept_src("policies", None))
    assert len(code) > 20_000 and b[0] == ["pre", code]
    assert b[1] == ["p", long.strip()] and len(b[2][1]) > 500 and len(b) == 903
