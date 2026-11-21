"""Fifteenth check: the phone menu's Send opens whenever it shows a number (r12 fix17 frame, audit15 questions 1)."""

from pathlib import Path

from test_fix13_send import FRAME, grab, node


def test_menu_send_press_and_paint_share_one_rule():
    btn = grab(FRAME, "function sendBtn(cls) {", "\n  }")
    assert "off = sendOff(cls)" in btn
    click = grab(FRAME, "if (d.send !== undefined) {", "return openSend();")
    assert "sendOff(" in click and "S.sendN" not in click


def test_saved_note_opens_from_the_menu_while_the_count_is_stale(tmp_path):
    """A saved note with the Questions refresh held: S.sendN is still 0, the saved drafts say 1; the menu shows Send 1 and must open."""
    lines = grab(FRAME, "  const sendNum = () =>", "cls !== 'hide-ph');")
    node(tmp_path, f"""
const assert = require('assert');
const S = {{sendN: 0, countsIn: true, stall: new Set()}};
let saved = 1;
const sendable = () => true, savedN = () => saved, sendP = {{saved: () => saved}};
{lines}
assert.strictEqual(sendNum(), 1, 'the menu paints Send 1');
assert.strictEqual(sendOff(''), false, 'so the menu press opens the sheet');
assert.strictEqual(sendOff('hide-ph'), false);
saved = 0;
assert.strictEqual(sendOff(''), true, 'a known zero still refuses on the phone');
assert.strictEqual(sendOff('hide-ph'), false, 'the desk Send opens at zero');
""")
