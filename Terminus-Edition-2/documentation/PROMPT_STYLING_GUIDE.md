# Instruction Prompt Styling

`instruction.md` is the main interface between the task and the agent. Edition 2 prompts should feel like realistic requests from engineers using terminal agents, Claude Code, Cursor, or similar tools.

Give the agent the what, not the how.

Important: prompts should not sound LLM-generated. Avoid verbose, repetitive, overly polite, highly formatted writing.

## Six Requirements

### 1. Concise

Use one sentence to three paragraphs in most cases. Avoid long prompts with many scattered requirements.

### 2. Well Specified

The goal must be clear. A human or agent should know what successful completion means.

### 3. Interesting

The task should be useful or interesting to a real group of developers or technical users.

### 4. No Answers or Hints

Do not include significant hints, detection guides, rubrics, or step-by-step solution instructions.

Requirements are allowed. Solution strategy is not.

### 5. Unique

The task must be noticeably unique relative to Terminal Bench 2, Terminal Bench 3, and Terminus Edition 1.

### 6. Absolute Paths

Good:

```text
/app/config/settings.json
```

Bad:

```text
config/settings.json
./settings.json
```

Also ensure `instruction.md` does not contain a canary string.

## Human-Centric vs Synthetic Style

| Dimension | Avoid | Prefer |
|---|---|---|
| Tone | "You are an expert programmer. Your goal is to..." | "We need to migrate the existing SQLite schema to..." |
| Length | 500+ words of redundant context | 150-200 words when a longer prompt is needed |
| Guidance | "First, use ls, then open..." | "The source data is in /data. Output to /app/output.json." |
| Formatting | many headings, bold markers, rubric-like bullets | plain technical prose |

## Common Prompting Errors

### Step-by-Step Walkthrough With Solution Values

Bad:

```markdown
Set SO_RCVBUF to 262144 bytes, set SO_SNDBUF to 262144 bytes, enable SO_REUSEADDR, and use 65536-byte chunks.
```

Why it fails: the prompt gives the exact solution.

### Hints Section That Describes the Answers

Bad:

```markdown
Look for currency conversion anomalies, transposed date fields, and period-boundary running-balance skips.
```

Why it fails: the prompt tells the agent where the corruption is.

### Excessive Markdown

Bad:

```markdown
##### /revenue-by-category GET
Fields: category, totalRevenue, orderCount...
```

Why it fails: it reads like structured documentation, not a realistic user prompt.

### Overly Prescriptive Structure

Bad:

```markdown
/app/backend/processor.py must export apply_grayscale, apply_rotate, apply_resize, and get_image_dimensions with these exact signatures...
```

Why it fails: it dictates implementation structure unless those public APIs are truly the user-facing requirement.

### Bold Markers Highlighting Solution Details

Bad:

```markdown
**Policy limit**: $500.
**Compliance Rate Definition**: 1.0 - (violation_count / total_expenses)
```

Why it fails: visual emphasis points the agent at solution details.
