---
name: Feature Request
about: Propose a new feature or enhancement
title: "[Feature] "
labels: ["enhancement"]
assignees: ""
---

## Problem Statement

<!-- What problem does this solve? Who has this problem? -->

## Proposed Solution

<!-- Describe the feature you'd like. Be specific about:
- User-facing behavior
- API changes (endpoints, schemas)
- Config changes
- UI changes
-->

## Alternatives Considered

<!-- What other approaches did you consider? Why is this the best? -->

## Implementation Notes

<!-- Technical details for implementers:
- Which routers/modules touched?
- DB migration needed? (append-only!)
- Provider gate impact?
- GPU/CPU considerations?
- Offline-first compliance?
-->

## Acceptance Criteria

- [ ] Offline-first preserved (no network calls in core path)
- [ ] Provider gate respected (cloud calls return 403 when offline)
- [ ] Tests added: unit + e2e scenario
- [ ] TypeScript types updated
- [ ] Docs updated (CHANGELOG, README, AGENTS.md if invariant)

## Related Issues / PRs

<!-- Link any related issues or PRs -->

## Priority

- [ ] Low (nice to have)
- [ ] Medium (important for workflow)
- [ ] High (blocking users)
- [ ] Critical (security/architectural)