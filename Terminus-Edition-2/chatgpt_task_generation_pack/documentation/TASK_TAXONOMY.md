# Task Type Taxonomy

Each task must have exactly one primary category in `task.toml`.

Categories describe the main theme or activity. Subcategories are a separate axis; see [TASK_SUBTYPES.md](TASK_SUBTYPES.md).

## Categories

### system-administration

OS-level configuration, user management, package management, processes, services, networks, or environments.

Examples: configure systemd, set user permissions, install Nginx.

### build-and-dependency-management

Compiling code, managing dependencies, or fixing build components.

Examples: fix build configuration, resolve dependency conflicts, set up multi-stage Docker builds.

### data-processing

Transforming, parsing, filtering, or aggregating datasets, files, and directories.

Examples: parse CSV, aggregate logs, filter JSON.

### games

Game-like or simulated terminal environments, interactive puzzles, or simulations.

Examples: VimGolf, terminal puzzles, text adventures.

### software-engineering

Developing or testing features and algorithms, fixing bugs, optimizing features, or maintaining projects.

Examples: caching algorithms, race conditions, database query optimization.

### machine-learning

Training, fine-tuning, inference, evaluation, dependency setup, or ML data pipelines.

Examples: fine-tune a model, debug training, optimize inference.

### debugging

Identifying, diagnosing, and fixing errors in scripts, codebases, or system configurations.

Examples: memory leaks, failing test suites, production crashes.

### security

Cryptography, authentication, permissions, vulnerability validation, exploit-style tasks, reverse engineering, or security configuration.

Examples: SQL injection, TLS settings, binary reverse engineering.

### scientific-computing

Scientific libraries or workflows, numerical computation, simulations, or domain research code.

Examples: numerical solvers, simulations, scientific optimization.

## Distribution Guidelines

- No single category should exceed about 30% of total tasks.
- At least four categories should each represent at least 10%.

## Choosing a Category

| Primary Activity | Category |
|---|---|
| OS or server configuration | `system-administration` |
| Build systems or packages | `build-and-dependency-management` |
| ETL or file processing | `data-processing` |
| Interactive challenge | `games` |
| Code development or testing | `software-engineering` |
| ML model work | `machine-learning` |
| Finding and fixing bugs | `debugging` |
| Security issue | `security` |
| Scientific code | `scientific-computing` |
