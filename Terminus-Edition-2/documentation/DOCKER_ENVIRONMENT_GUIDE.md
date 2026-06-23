# Creating the Docker Environment

The Dockerfile sets up the task environment. It must live in `environment/`, be reproducible, stay lightweight, and run without privileged mode.

## Basic Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    pandas==2.1.0 \
    requests==2.31.0

COPY app/ /app/

ENV PYTHONPATH=/app
```

## Key Principles

### Pin Application Dependencies

Good:

```dockerfile
RUN pip install numpy==1.26.4
```

Bad:

```dockerfile
RUN pip install numpy
RUN pip install numpy>=1.0
```

System packages should be pinned where behavior changes matter. Common apt packages do not always need exact pins.

### Pin Base Image Tags

Good:

```dockerfile
FROM python:3.11-slim
```

Bad:

```dockerfile
FROM python:latest
```

Digest pins are not required, but are allowed.

If using Docker Compose, every `image:` line should use a specific version tag.

### Never Copy Solution or Tests

Bad:

```dockerfile
COPY solution/ /solution/
COPY tests/ /tests/
```

The harness mounts solution and tests at runtime.

### No Privileged Mode

Bad:

```yaml
services:
  task:
    privileged: true
```

### Keep Images Lightweight

- Use slim base images when possible.
- Clean apt cache.
- Avoid unnecessary packages.

## docker-compose.yaml

Single service example:

```yaml
version: "3.8"
services:
  task:
    build: .
    working_dir: /app
    environment:
      - PYTHONPATH=/app
```

Multi-service example:

```yaml
version: "3.8"
services:
  app:
    build: .
    depends_on:
      - db
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/app

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=app
```

If using compose, set `custom_docker_compose = true` in `task.toml`. If there are multiple services, set `is_multi_container = true`.

## Common Patterns

Python:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ /app/src/
ENV PYTHONPATH=/app
```

Node.js:

```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY src/ /app/src/
```

Git repository:

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/example/repo.git /app \
    && cd /app && git checkout abc123def
```

Pin cloned repositories to a specific commit so agents cannot see future commits with solutions.

## Troubleshooting

Build locally:

```bash
cd environment
docker build -t my-task .
docker run -it my-task bash
```

Check compose logs:

```bash
docker-compose logs
```

CI validates:

- `pinned_dependencies`
- `tests_or_solution_in_image`
- `check_dockerfile_references`
- `check_privileged_containers`
