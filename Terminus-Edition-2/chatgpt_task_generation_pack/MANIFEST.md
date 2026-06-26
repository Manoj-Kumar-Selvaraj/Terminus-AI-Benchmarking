# ChatGPT Task Generation Documentation Pack

This package is intended to be attached to ChatGPT when generating new Terminus Edition 2 / Terminal-Bench 3.0 tasks.

## Primary Prompt

- `chatgpt-task-generation-context.md`

Use this as the main copy/paste context. It contains the task-generation prompt, quality requirements, language-specific guidance, validation expectations, and self-audit checklist.

## Core Documentation

- `documentation/`

This folder contains the repository's authoring guidance, including task requirements, milestone structure, Docker and verifier rules, oracle expectations, rubric guidance, CI/LLMaJ references, review guidance, and submission checklists.

Important files include:

- `documentation/TASK_REQUIREMENTS.md`
- `documentation/MILESTONES_GUIDE.md`
- `documentation/WRITING_TESTS_GUIDE.md`
- `documentation/ORACLE_SOLUTION_GUIDE.md`
- `documentation/MILESTONE_ORACLE_SOLUTION_RULES.md`
- `documentation/RUBRICS_GUIDE.md`
- `documentation/SUBMISSION_CHECKLIST.md`
- `documentation/CI_CHECKS_REFERENCE.md`
- `documentation/LLMAJ_CHECKS_REFERENCE.md`
- `documentation/AGENT_REVIEW_REFERENCE.md`
- `documentation/COMMON_ERRORS.md`
- `documentation/REVISION_AVOIDANCE_PLAYBOOK.md`

## Reference Tasks

The reference tasks are included for file structure, milestone mechanics, verifier style, and task packaging conventions. They should not be cloned conceptually.

- `references/template-go-matcher-milestone/`
  - Structural milestone template. Use only for layout and wrapper conventions. Do not use its matcher/reconciler premise unless explicitly requested.
- `references/go-notification-dispatcher-stability/`
  - Go service stability/reference behavior task.
- `references/go-edge-gateway-tls-recovery/`
  - Go HTTP/TLS recovery and runtime behavior reference.
- `references/go-tenant-route-service-recovery/`
  - Go service recovery reference with system-oriented debugging flow.
- `references/k8s-invoice-batch-rbac-recovery/`
  - Kubernetes/RBAC operational incident reference.
- `references/java-billing-service-container-health/`
  - Java container health and production service reference.

## Terminal-main Reference Bundle

- `terminal_main_reference/`

This folder is copied from `Terminal-main (1)/Terminal-main` because it contains the standalone ChatGPT/web authoring guidance and hard-task research material.

Included:

- `terminal_main_reference/web/`
  - ChatGPT/web task authoring playbook, task creation guide, proposal rubric, bulk idea generation guidance, seed refinement, and implementation-collapse audit guidance.
- `terminal_main_reference/docs/`
  - Terminal-Bench 3.0 / Edition 2 submission guide, hard-but-fair authoring guidance, category profiles, failure catalog, architecture notes, and reference task template docs.
- `terminal_main_reference/prompts/`
  - Multi-step prompt pipeline and seed-bank material for generating and screening hard task ideas.
- `terminal_main_reference/specs/`
  - Example high-difficulty task specs and validation logs.
- `terminal_main_reference/fixture_tasks/`
  - A small set of fixture/reference tasks for structural inspection.

Use these files as high-priority guidance when asking ChatGPT to ideate or screen tasks. If there is a conflict between older local notes and `terminal_main_reference/web/terminal-bench-task-creation.md`, prefer the stricter rule.

## Exclusions

This pack intentionally excludes:

- auto-evaluation logs
- old archives
- submission ZIPs
- bulk generated per-task docs
- local caches
- unrelated task corpus folders

The goal is a compact, high-signal reference package that improves task quality without encouraging copy/paste task design.

