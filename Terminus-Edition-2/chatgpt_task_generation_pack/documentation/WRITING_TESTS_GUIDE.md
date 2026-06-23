# Writing Tests

`tests/test_outputs.py` contains pytest tests that verify task completion. Good tests are the foundation of a quality task.

For milestone tasks, tests live under `steps/milestone_N/tests/`.

## Basic test_outputs.py

```python
"""Tests for the data processing task."""

import json
from pathlib import Path


def test_output_file_exists():
    """Verify the output file was created."""
    assert Path("/output/result.json").exists()


def test_output_format():
    """Verify the output has correct JSON structure."""
    with open("/output/result.json") as f:
        data = json.load(f)

    assert "status" in data
    assert "items" in data
    assert isinstance(data["items"], list)
```

## Key Principles

### Test Behavior, Not Implementation

Good:

```python
def test_function_handles_empty_input():
    """Empty input should return an empty list."""
    from app.main import process

    assert process("") == []
```

Bad:

```python
def test_has_empty_check():
    """Check if code has empty input handling."""
    source = open("/app/main.py").read()
    assert "if not" in source
```

### Use Informative Docstrings

Every test must have a docstring explaining what behavior it checks.

### Match Task Requirements

Tests should cover:

- explicit requirements
- implicit expected behavior
- critical edge cases

Every prompt requirement should map to a test.

### Cover Edge Cases

Include boundaries, not just happy paths:

- empty input
- single-item input
- large input
- special characters
- invalid data
- malformed requests
- missing files

## tests/test.sh

The test runner installs test dependencies, runs pytest, and writes reward.

```bash
#!/bin/bash
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi

uvx \
  -p 3.13 \
  -w pytest==8.4.1 \
  -w pytest-json-ctrf==0.3.5 \
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

Test dependencies belong in `tests/test.sh`, not in the Dockerfile.

## Common Patterns

File output:

```python
def test_csv_output():
    """Verify CSV output format and content."""
    import csv

    with open("/output/data.csv") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) > 0
    assert "id" in rows[0]
```

API endpoint:

```python
def test_health_endpoint():
    """Health endpoint returns 200."""
    import requests

    response = requests.get("http://localhost:8080/health")
    assert response.status_code == 200
```

Database state:

```python
def test_database_populated():
    """Database contains expected records."""
    import sqlite3

    conn = sqlite3.connect("/app/data.db")
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()

    assert count == 100
```

Command output:

```python
def test_cli_help():
    """CLI shows help message."""
    import subprocess

    result = subprocess.run(
        ["python", "/app/cli.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
```

## Anti-Patterns

- brittle exact string matching
- hardcoded random values
- order-dependent tests
- tests that parse source code instead of behavior
- tests that expose answers
- tests that rely on live network

CI validates `behavior_in_tests`, `behavior_in_task_description`, `informative_test_docstrings`, and `ruff`.
