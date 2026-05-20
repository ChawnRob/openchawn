# OpenChawn Smoke Test Checklist

Use this checklist **before opening a PR** and **before promoting staging to production**.

Repo: `/Users/chawn-mbp-15/projects/openchawn`  
Local app: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` → `http://127.0.0.1:8000/`

Mark each item **PASS / FAIL / N/A** and note failures in the PR description.

---

## Local — runtime

| # | Check | PASS / FAIL |
|---|--------|-------------|
| 1 | **App starts locally** — uvicorn starts without traceback | |
| 2 | **Homepage loads** — `GET /` returns 200, page renders | |
| 3 | **COCO / OpenChawn interface loads** — header, empty state or chat shell visible | |

---

## Local — UI / composer

| # | Check | PASS / FAIL |
|---|--------|-------------|
| 4 | **Message input works** — can type and send a message | |
| 5 | **Mobile composer works** (≤640px) — input usable, no overlap, safe-area OK | |
| 6 | **Microphone icon visible** if expected for current UX mode | |
| 7 | **No visible desktop grid bug** (≥641px) — background grid hidden on desktop light mode | |
| 8 | **Desktop cockpit/emblem** (≥641px) — emblem/LED visible when chat_clean desktop rules apply | |

---

## Local — chat / language

| # | Check | PASS / FAIL |
|---|--------|-------------|
| 9 | **Provider response works** — assistant reply after send (guest or authenticated) | |
| 10 | **Language auto mode works** — reply matches user language intent | |
| 11 | **No forced French** unless user writes French — English in → English out | |

---

## Local — automated (light)

| # | Check | PASS / FAIL |
|---|--------|-------------|
| 12 | ` .venv/bin/python -m pytest -q` — all pass | |
| 13 | ` .venv/bin/python scripts/test_no_forced_french_runtime.py` — OK | |

---

## Browser / console

| # | Check | PASS / FAIL |
|---|--------|-------------|
| 14 | **No console critical error** on load and after one chat send | |

---

## Staging vs production

| # | Check | PASS / FAIL |
|---|--------|-------------|
| 15 | **Railway staging URL responds** — health/homepage OK on staging service | |
| 16 | **Production URL remains untouched** until explicit approval — no prod deploy from unmerged branch | |

---

## Sign-off

- **Tester:** _______________  
- **Date:** _______________  
- **Branch / commit:** _______________  
- **Staging URL tested:** _______________  
- **Ready for PR / prod promotion:** YES / NO
