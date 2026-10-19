# ADDENDUM 02: Working With the Monitor Session

**Read order:** `BUILD.md` -> `CLAUDE.md` -> `ADDENDUM-01-cloud-pivot.md` -> this file.
**Precedence:** Where this file conflicts with earlier files, this file wins. Anything not mentioned here still applies.

---

## 1. What changed

A second Claude session, the **monitor**, now runs alongside you. It follows `MONITOR.md`. It reviews your work, tests the app, researches, ideates and prepares the pitch. It never edits product code. It sends you actionable items through `monitor/INBOX.md`.

You remain the only session that writes product code, data, and `PROGRESS.md`.

## 2. File ownership

| File | Owner | You may |
|---|---|---|
| `backend/`, `frontend/`, `scraper/`, `scripts/`, `data/`, `PROGRESS.md` | Builder (you) | Read and write |
| `monitor/*` | Monitor | Read only. Never edit |
| `BUILD.md`, `CLAUDE.md`, `ADDENDUM-*.md`, `MONITOR.md` | Humans | Read only |

Commit often (after every passing task) so the monitor can review clean diffs. Use commit messages that start with the task ID, for example `T1.4: hybrid retrieval with BM25 fusion`.

## 3. Additions to the build loop

Insert into the CLAUDE.md loop, after the Step 0 added by Addendum 01:

- **Step 0b, INBOX:** Read `monitor/INBOX.md`.
  - Any open **P0**: handle it now, before picking a new task. It counts as a task and goes through the full loop.
  - Open **P1**: handle at the next task boundary, one at a time, if effort is S or M.
  - **P2**: only during improvement passes (CLAUDE.md section 6).
- **Step 8, LOG, also:** for every inbox item you act on, add a line to the task's PROGRESS.md block:
  ```
  Inbox: M-007 done (evidence: ...) | M-009 rejected (reason: ...) | M-010 deferred to improvement pass
  ```
  The monitor verifies `done` items itself. If it reopens one, treat the reopened item like a new P0 or P1 per its priority.

## 4. Judging and rejecting inbox items

You may reject an item, but only with a written reason in PROGRESS.md. Valid reasons:
- It conflicts with a non-goal or a rule in an addendum.
- It would put a working demo step at risk this late.
- The evidence does not reproduce. Include what you ran.

Never silently ignore an item. Never implement an item that would break a rule in CLAUDE.md or an addendum, even if the monitor filed it. Reject it with the reason instead.

## 5. Shared environment rules

- Keep the dev server running on its normal ports during work so the monitor can test against it.
- If the monitor starts its own server it uses port `8100`. Do not use that port.
- Do not reset the database or Chroma folder without logging it in PROGRESS.md first, because the monitor may be mid-test.

## 6. Additions to the review checklist

- [ ] No open P0 in `monitor/INBOX.md` when marking a task done.
- [ ] Every inbox item you touched has a status line in PROGRESS.md.
- [ ] Commit made with the task ID prefix.
