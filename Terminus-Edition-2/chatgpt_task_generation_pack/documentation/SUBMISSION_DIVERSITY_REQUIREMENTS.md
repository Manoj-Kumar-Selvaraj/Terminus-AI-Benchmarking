# Submission Diversity Requirements

Project Terminus Edition 2 includes diversity requirements that restrict new submissions to improve dataset variety.

These checks apply to brand-new submissions moving forward. Tasks already waiting for review or already in a revision queue are not affected.

## Current Restrictions and Preferences

### Codebase Size

Only `small` and `large` are accepted for new submissions.

`minimal` is blocked.

Codebase size is based on files in `environment/`:

- `minimal`: 0-20 files
- `small`: 20+ files
- `large`: 200+ files

### Milestones

Non-milestone tasks are not blocked, but milestone tasks are preferred.

### Model Difficulty

Only medium and hard tasks are accepted.

Easy tasks are blocked.

This refers to model performance pass rates, not merely the `difficulty` value in `task.toml`.

### Category and Subcategory

There are no category or subcategory restrictions.

### Languages

All languages are accepted.

Python tasks must be hard by model difficulty to be accepted.

## Practical Pre-Submission Check

- [ ] `codebase_size` is `small` or `large`.
- [ ] Expected model difficulty is medium or hard.
- [ ] If the task is Python-heavy, expected model difficulty is hard.
- [ ] Milestones were considered if the task is naturally sequential.
- [ ] Category and subcategory are accurate.
