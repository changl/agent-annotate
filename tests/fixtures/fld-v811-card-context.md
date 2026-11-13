---
title: FLD card context
other_files_required: none
---

## Private messages: less in the way, drawn; past events on the phones: built

Your #38873 and #38874 notes, drawn on both phones; and the phones now follow the web on past events. Sections 1 and 2 are drawings only: nothing is built until you pick. Section 3 and the iPhone lock are built and their checks pass. Nothing has merged; testers are unchanged. Test names and data throughout. [Card text](../../../reports/ui-round-9/card.md) · [Report](../../../reports/ui-round-9/report.md)

**1. Messaging with the least in the way.** Each strip shows today on top and the proposal under it. Counts are the screens and waits a member meets, the taps, and the words on them.

| | Today (iPhone / Android) | Proposed |
|---|---|---|
| First private message, on your usual phone | 3 screens, 1 wait, 3 taps, 155 / 145 words | 2 screens, no wait, 2 taps, 53 / 59 words |
| Signing in on a new phone, until it reads and sends | 5 screens, 2 waits, 6 taps, 351 / 314 words | 3 screens, 1 wait, 3 taps, 157 / 156 words |
| A message whose keys are still arriving | "Waiting for this message." / "Confirm this phone to read this message." | A quiet grey bubble with no words that fills in by itself |

- **Proposed** keeps the security you approved (card 21344): the recovery key, "Is this you signing in?" on the other phone, and emoji compared on both. The key is made in the background after sign-in; on the first Message tap the member saves it in two taps and the chat opens. A new phone asks the other phone by itself; Chat shows one quiet line, "Confirm on your other phone".
- **Option 1, key later:** the chat opens at once and the key is saved later, from one line in Chat. *If the phone is lost before then, older private messages are gone.*
- **Option 2, one sheet:** the other phone shows the emoji on the "Is this you signing in?" sheet, so one tap says both "it's me" and "they match" (2 screens, 2 taps). *A hurried tap approves both.*

![iPhone: today vs proposed, with both options](assets/8cf7f4b0bb96-e5ii-ios.png)

![Android: today vs proposed, with both options](assets/e84c0a2c30de-e5ii-and.png)

```ask
#38884 Which messaging path should we build?
Drawings only. Whatever you pick is built on both phones, then shown to you again before it merges.
+ Proposed: Fewer screens and taps, no wait before the first message, and the security you approved stays as it is.
- Proposed plus key later: The chat opens at once; the key waits for later. Older messages are lost if the phone goes before the key is saved.
- Proposed plus one sheet: One tap fewer on a new phone; one hurried tap approves both questions.
- Proposed plus both options: Fewest steps; both risks above.
impact: high
```

**2. The new phone, when it isn't confirmed.** One page, the same whether the other phone tapped No, never answered or was closed. Neither version says what the other phone did, and both say what the member can do next. The page still comes sooner after a No (at once) than after no answer (2 minutes); hiding that too would make the real member wait 2 minutes, so it isn't drawn. The real protection, signing the new phone out after a No, is part of the sign-in security work still waiting on you (FLD-tm0m).

![New phone, not confirmed: A and B on both phones](assets/a6ab35d8be15-2yji.png)

```ask
#38885 Which wording for a new phone that isn't confirmed?
Same page on both phones, built after you pick.
+ B, "This phone isn't confirmed yet": A plain phone icon, "Private messages stay locked on this phone until it's confirmed. Nothing was shared with it." Keeps the "I can't do either" link for members with no other phone and no key.
- A, "Not confirmed": A red warning icon, "This phone was not confirmed, so it still can't read or send private messages." No "I can't do either" link.
impact: medium
```

**3. Past events on the phones.** As on the web: once an event has ended, a registered member's "You're registered" card no longer shows CHANGE and CANCEL, and Android's extra "Cancel booking" bar on past events is gone. Upcoming events are unchanged; no new words or layout. Top row is today's main, bottom row is the fix. A new test on each phone fails on today's main and passes with the fix; both phone checks pass.

![iPhone event page, before and after](assets/6203a40a1ad0-gzab-ios-before-after.png)

![Android event page, before and after](assets/fe3d0d851d95-gzab-android-before-after.png)

```ask
#38886 Merge past events on both phones?
iPhone and Android, in the next merge for each phone.
+ Approve: Both merge. Testers get it with the next upload you approve.
- Hold: Nothing merges. Say what to change.
impact: low
```

**4. iPhone: the lock in the chat list.** A phone that isn't confirmed yet shows "Locked until you confirm this phone" in the chat list. Android draws the thin outline lock before it (approved on #38872); the iPhone now does too. At 130 % text the two rows broke at different words in the first picture, because some digits in the time are wider than others; the times now use same-width digits, so both rows break at the same word. Top is today's main, bottom is the fix, at normal and 130 % text. The test fails on today's main and passes with the fix; the iPhone check passes.

![iPhone chat list lock, before and after](assets/51dc2a85f921-xv40o-lock-before-after.png)

```ask
#38887 Merge the iPhone chat-list lock?
iPhone only. It's on the same branch as the narrow stop box (#38879) and merges in the next iPhone merge.
+ Approve: It merges. Testers get it with the next iPhone upload you approve.
- Hold: Nothing merges. Say what to change.
impact: low
```
