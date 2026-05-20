# OpenChawn Sandbox Workflow

Official repo: `/Users/chawn-mbp-15/projects/openchawn`  
Remote: `https://github.com/ChawnRob/openchawn.git`

This document defines how to test OpenChawn safely without touching production.

## Branch roles

| Branch | Role |
|--------|------|
| **`main`** | **Production only.** What Railway production deploys after review. |
| **`sandbox/staging-v11-7`** | **Safe test branch** for staging work, docs, and pre-production validation. |

Do **not** use experimental clones (Claude project folders, `email-world-agent`, duplicate paths).

## Rules

1. **`main` = production only**  
   No direct commits for experiments. No “quick fixes” pushed straight to `main`.

2. **`sandbox/staging-v11-7` = safe test branch**  
   All non-trivial work starts here (or a short-lived feature branch cut from it).

3. **No direct push to `main`**  
   Use pull requests only. Human review before merge.

4. **All changes go through PR**  
   Even documentation and workflow updates should use a PR when they affect team process.

5. **Local test required before PR**  
   - Working tree clean before branch work  
   - `.venv` tests and smoke scripts (see `docs/SMOKE_TEST_CHECKLIST.md`)  
   - Local UI check at `http://127.0.0.1:8000/` when UI changes

6. **Railway staging deployment required before production deployment**  
   - Validate on **staging** URL first  
   - Only after staging passes: merge to `main` and allow production deploy

7. **Rollback rule**  
   Production can be restored from the **last stable tag** (e.g. `v11.6.3-stable`, `v11.7-ux`).  
   Do not retag production without recording what was rolled back and why.

## Typical flow

```text
main (production)
  ↑ merge PR (after review + staging OK)
sandbox/staging-v11-7 (or feature/* from sandbox)
  ↑ push + PR
local dev + smoke tests
```

## What not to do

- Push untested code to `main`
- Deploy production from a laptop without staging sign-off
- Edit Railway **production** variables or services without explicit human approval
- Work from `/Users/chawn-mbp-15/Documents/Claude/Projects/openchawn` or other non–source-of-truth paths

## Related docs

- `docs/SMOKE_TEST_CHECKLIST.md` — pre-PR and pre-deploy checks  
- `docs/DEPLOYMENT_RULES.md` — Railway and release discipline  
- `OPENCHAWN_SOURCE_OF_TRUTH.md` — repo path and deploy target
