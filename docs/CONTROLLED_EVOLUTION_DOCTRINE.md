# OpenChawn Controlled Evolution Doctrine

## Purpose

This document defines the controlled internal evolution doctrine for OpenChawn.

Its purpose is to let OpenChawn improve over time by observing its own behavior, analyzing failures, evaluating memory and routing quality, and generating structured improvement proposals, while preventing uncontrolled self-modification.

Core rule:

Nothing autonomous, irreversible, untraceable, untestable, or non-repairable is allowed.

## Principles

Every internal improvement path must remain:

1. Observable
2. Explainable
3. Testable
4. Reversible
5. Versioned
6. Audited
7. Human-approved before production
8. Recoverable through rollback

OpenChawn may learn from its behavior, but it must not silently rewrite itself.

## Allowed Actions

OpenChawn may:

- observe runtime behavior
- analyze logs, conversations, memory events, provider failures, UX feedback, and regression patterns
- detect recurring problems
- generate improvement proposals
- create structured tickets
- suggest prompt, memory, routing, UX, or architecture improvements
- generate patch drafts
- run sandbox tests
- compare candidate versions against a stable baseline using measurable evaluation

These actions are advisory, analytical, or sandboxed. They are not authorization to modify production autonomously.

## Forbidden Actions

OpenChawn must not:

- modify production code directly without human approval
- push to `main` without human validation
- deploy to production autonomously
- overwrite stable Git tags
- delete critical memory without backup and audit trail
- change owner/public access rules without approval
- change provider routing in production without tests and approval
- alter system prompts or safety rules silently
- perform any action that cannot be explained, reversed, tested, or repaired

## Evolution Pipeline

```text
[Runtime Usage]
    ↓
[Observation Layer]
    - logs
    - errors
    - latency
    - cost
    - user feedback
    - memory events
    - provider responses
    ↓
[Evaluation Layer]
    - quality scoring
    - regression detection
    - contradiction detection
    - failed intent detection
    - provider performance analysis
    - memory usefulness scoring
    ↓
[Improvement Proposal Layer]
    - structured proposal only
    ↓
[Sandbox Execution Layer]
    - isolated tests
    - baseline comparison
    - regression blocking
    ↓
[Human Approval Gate]
    - Robert or authorized maintainer approval
    - no silent merge
    - no autonomous production release
    ↓
[Git Versioning Layer]
    - explicit commit message
    - version attachment
    - stable tag only after validation
    - rollback path required
    ↓
[Deployment Layer]
    - deploy only after approval
    - monitor after deploy
    - rollback if health checks fail
```

## Proposal Schema

Each improvement proposal must include:

- `proposal_id`
- `problem`
- `evidence`
- `affected_module`
- `proposed_change`
- `expected_benefit`
- `risk_level`
- `rollback_plan`
- `test_plan`
- `target_version`

Recommended additional fields:

- `baseline_version`
- `owner`
- `created_at`
- `approval_status`
- `evaluation_metrics`

## Rollback Rules

Every approved change must have a rollback path before production deployment.

Rollback rules:

- rollback plan must be written before merge or deploy
- rollback target must reference a known good commit, tag, or release marker
- rollback must be executable without relying on undocumented tribal knowledge
- destructive memory changes require backup plus audit trail
- if health checks fail after deploy, rollback is preferred over speculative hot-patching

No production change is complete unless recovery is possible.

## Git And Versioning Rules

- all implementation changes must use explicit commits
- every approved evolution must attach to a version target such as `V11.7.x`, `V11.8`, or `V12`
- stable tags are created only after validation
- stable tags must never be overwritten
- patch drafts and experiments must remain traceable to their source proposal
- no hidden or silent architecture changes are allowed

## Production Safety Rules

- production self-modification is forbidden
- production deployment is never triggered autonomously by the system
- provider routing changes require tests before approval
- system prompt and safety rule changes require explicit review
- critical memory deletion requires backup, audit, and approval
- experimental evaluation must run in sandbox or isolated validation paths, not directly in production

## Human Approval Requirements

Before production, each improvement must be reviewed and approved by Robert or an authorized maintainer.

Approval gate requirements:

- proposal reviewed
- evidence checked
- test plan accepted
- rollback plan accepted
- risk understood
- human approval recorded before push/deploy decision

No silent merge. No silent deploy. No silent policy drift.

## Example Improvement Proposal

```yaml
proposal_id: evo-2026-05-12-memory-recall-001
problem: "Relevant memories are not consistently surfaced for repeated project questions."
evidence:
  - "Memory hit rate dropped from 0.62 to 0.41 over the last 7 days."
  - "Regression sample shows repeated failure to retrieve project-specific summaries."
affected_module:
  - "app/memory/fractal_memory.py"
  - "app/memory/retrieval_policy.py"
proposed_change: "Adjust retrieval policy thresholds and add a sandbox evaluation for project-memory recall."
expected_benefit: "Higher useful-memory recall without changing the external chat contract."
risk_level: "medium"
rollback_plan: "Revert to the previous retrieval policy commit and restore the prior threshold values."
test_plan:
  - "Run sandbox replay against stable baseline."
  - "Measure recall, contradiction rate, latency, and regression count."
target_version: "V11.7.x"
approval_status: "pending_human_review"
```

## Rule

No memory, routing, prompt, UX, or architecture improvement should be considered production-ready unless it is:

- documented
- tested
- reversible
- versioned
- human-approved

OpenChawn may propose evolution.
OpenChawn may not execute uncontrolled evolution.

