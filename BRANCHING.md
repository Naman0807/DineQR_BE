# dineQR Branching Strategy (MANDATORY)

This document defines the branching workflow for this repository. ALL developers and AI assistants MUST follow these rules.

## Branches

- `main` → production. Stable, always deployable. NEVER commit directly.
- `dev` → shared integration base. ALL new work branches off `dev`. ALL completed features merge back into `dev`.
- `feature/<short-description>` → short-lived feature branches, one per task.

## Core Rules

1. `main` is production. NEVER commit directly to it. It is only updated from `dev` (by the lead).
2. `dev` is the shared integration base. ALL new work branches off `dev`. ALL completed features merge back into `dev`.
3. Feature branches are short-lived, named `feature/<short-description>`, one per task.
4. NEVER work directly on `dev` or `main` — always on a feature branch.
5. Before starting ANY task: `git checkout dev` then `git pull origin dev`, then create a feature branch.
6. When a feature is complete and tested: merge feature → `dev`, push `dev`.
7. NEVER push a feature branch to origin, create a PR, or merge into `dev`/`main` until the user explicitly approves it. Work locally on the feature branch and wait for approval.

## Definition of Done (merge gate)

Before any feature branch merges into `dev`, ALL of the following MUST be true:
- [ ] Code builds without errors (frontend: `npm run build`; backend: imports clean)
- [ ] No broken endpoints (backend: smoke test passes)
- [ ] Tests pass (once tests are added)
- [ ] Feature branch is up to date with `dev` (rebased/merged)
- [ ] User explicitly approved the push/PR/merge
- [ ] PR/merge created into `dev`

## Sync Ritual (for multiple developers)

1. ALWAYS `git checkout dev` + `git pull origin dev` before creating any feature branch.
2. Before merging a feature into `dev`, first pull the latest `dev` and resolve conflicts locally.
3. NEVER force-push to `dev` or `main`.