cd /mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2 || exit 1

for z in All-New-Tasks-Zips-20260528/*.zip; do
  t="${z##*/}"
  t="${t%.zip}"
  task=""

  for b in Manual-Task-Batch-20260528 Manual-Task-Batch-20260528-Extra5 Manual-Task-Batch-20260528-RubyExtra5 New-Cobol-Tasks; do
    c="$b/$t"
    if [ -f "$c/task.toml" ]; then
      task="$c"
      break
    fi

    if [[ "$t" == *-earliest-date-priority ]]; then
      base="${t%-earliest-date-priority}"
      c="$b/$base"
      if [ -f "$c/task.toml" ]; then
        task="$c"
        break
      fi
    fi
  done

  if [ -z "$task" ]; then
    echo "SKIP (task folder not found): $t"
    continue
  fi

  echo "===== $task ====="
  ./scripts/terminus2_cli.sh preflight "$task" || exit 1
  ./scripts/terminus2_cli.sh oracle "$task"   || exit 1
  ./scripts/terminus2_cli.sh nop "$task"      || exit 1
done