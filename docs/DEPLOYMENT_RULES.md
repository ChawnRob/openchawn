# OpenChawn Deployment Rules

Production target: **Railway** (service tied to `main`).  
Source of truth: `/Users/chawn-mbp-15/projects/openchawn`

## Core rules

1. **Never deploy directly from untested changes**  
   Local smoke tests + staging deploy must pass first (`docs/SMOKE_TEST_CHECKLIST.md`).

2. **Never edit Railway production variables without explicit human approval**  
   API keys, provider config, `DATABASE_URL`, feature flags, and CORS origins are production-critical.

3. **Never switch production service / branch / root directory without approval**  
   One production service, one approved deploy path from `main`.

4. **Never merge to `main` without PR review**  
   No force-push to `main`. No bypass of review for “small” changes.

5. **Tag stable releases**  
   Examples: `v11.6.3-stable`, `v11.7-ux`, future `v11.7.0`.  
   Tags mark rollback points; document what each tag contains.

6. **Use staging first, then production**  
   ```text
   sandbox/staging-v11-7 → Railway staging → PR → main → Railway production
   ```

## Branch and environment map

| Environment | Git branch | Purpose |
|-------------|------------|---------|
| **Production** | `main` | Live users, `www.openchawn.com` |
| **Staging / sandbox** | `sandbox/staging-v11-7` (or PR branches) | Pre-prod validation |

## Railway discipline

- **Staging:** deploy from sandbox branch or PR preview per team setup; run full smoke checklist on staging URL.
- **Production:** deploy only after merge to `main` and explicit go-ahead.
- **Rollback:** redeploy last known-good tag or commit on `main`; record incident in team notes.

## Forbidden without approval

- Pointing production Railway at a non-`main` branch
- Changing `Procfile`, start command, or port binding on production without review
- Sharing or committing `.env` / secrets
- Deploying from Claude experimental folders or duplicate repos

## Related docs

- `docs/SANDBOX_WORKFLOW.md` — branch workflow  
- `docs/SMOKE_TEST_CHECKLIST.md` — verification steps  
- `OPENCHAWN_SOURCE_OF_TRUTH.md` — canonical paths
