---
title: Rebex card context
other_files_required: none
---

## Status

**Rebex is live on rebexcutlery.com** (new theme published 2026-11-10 20:01Z), **and the checkout now matches it** (D35).

**#160 starting screenshots: you approved all 30** (05:14Z): home, Burnt Damascus collection, 8.5" Burnt Damascus Chef page, empty cart and privacy policy, in Safari, Firefox and Chrome, at phone and desktop width. They are now the reference pictures for every later test run (receipt `run18-owner-approval.json`). They are now recorded in the test system on both Macs. The full local CI found that #160 conflicts with the latest main in 3 files; fixed. **#160 is merged** (07:21Z): independent review approved and the full local CI passed on the final version, tested together with the latest website code.

**Phase C: you chose staged** (05:41Z). The offline build is done and passes (11:42Z): the independent review approved it after three safety fixes, and the full local CI passed. Its pilot needed more requests than the normal limits allow, so I kept the normal limits and split the home-page pilot into two halves (390+1440 and 750+990 wide). Both halves run back to back inside your one hour on rebex-new; if the second half can't finish within the hour, it stops and I report. The code now enforces that hour itself (hard stop at the end, second half only if time allows), approved and checked. The first start (14:32Z) didn't run: the worker sent it through the wrong entry point, and the safety check refused it before any page was loaded (zero store requests). I released the store at 14:48Z. The corrected start ran at 15:43Z. The 390 and 1440 widths were captured, but a browser self-check in Safari's engine stopped the run after about 7 minutes. It used 11 page requests, well under the limits. The second half (750/990) was correctly not started, so there are no tablet screenshots yet. I released the store at 15:50Z.
- **Cause, found offline (likely, not certain):** a test bug, not a site bug. After the password page, the test briefly ran the home page's scripts as if they were still on the password page's address. A theme script then fetched the wrong address and failed in Safari. The browser installs are unchanged since the offline checks passed.
- **Fix:** the test now answers the password step with an empty page and runs the home page only at its real address. Offline, the old code reproduces the error and the fix clears it, while a real home-page failure still stops the run. Limits are unchanged. It is being committed and goes through the same review and full offline CI before any store use.
- **Measured:** Safari took about 4.5 minutes for two widths, so both halves fit in an hour with room to spare.
- **You allowed one more hour** (#236, 16:38Z). The fix passed independent review, the full offline CI and my own offline check. The pilot ran at 17:14Z. Safari got through both widths this time. Then Firefox, on its first page, logged script-loading errors for Shopify's and the theme's own modules, and the run was stopped there (12 page requests). The second half didn't start, so there are no tablet screenshots yet. I released the store at 17:21Z.
- **Cause, checked offline:** all 42 Firefox errors are the same 9 messages seen in the earlier runs and in a plain Firefox on the live site. They come from Firefox and Shopify's script loading, not the theme or the test. The earlier runs only noted them; they were never marked as known for strict runs, so the pilot treated them as new.
- **Fix:** mark exactly those 9 messages as known, and only in Firefox, on the home page, at the four widths. Any other or new error still stops the run; offline, an added new error still stopped it. Limits are unchanged. The full offline CI passed, but the independent review found that the "home page only" condition could also have matched the password page, so the fix is being tightened and re-checked.
- **Measured:** Safari took about 4 minutes for both widths and used 8 of its 32 page requests.

```ask
#238 Allow one more 1-hour home-page pilot on rebex-new, after the Firefox fix passes review and offline CI?
The second hour also ended early, on a test rule, after 12 page requests; Safari now passes. Same limits, same two halves, read-only, rebex-new only.
+ Yes, up to 2 more hours: if the next one stops on another test issue, its fix goes through the same review and checks, then one last hour runs without asking you again.
- One more hour only: any further stop comes back to you.
- Not now: Phase C waits; nothing more runs on the store.
```

**New 4-piece cutout and your image choices since Nov 11: live on both stores, verified** (06:58Z). Spice, 15-pc German, 15-pc Damascus with block, 5-pc, 4-pc and 4-pc set meat cleaver now match your catalog order exactly at phone and desktop width; the 4-pc opens with your selected in-use photo, and the new cutout has the same gray tile as the other cutouts. The 5-pc dimensions card was cropped to one cleaver, so it now shows whole (first and last sections visible). Images you unchecked are off the galleries, still in Shopify Files. The 8-pc Burnt Damascus catalog candidate was left alone: its live listing is one of the 25 protected live-only products. 18 live writes, no errors, nothing deleted.
