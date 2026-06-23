#!/usr/bin/env bash
set -euo pipefail
python3 - <<'SOLVEPY'
import json
from pathlib import Path
mapping = Path('/app/config/event_source_mapping.json')
data = json.loads(mapping.read_text())
data['enabled'] = True
data['function_name'] = 'payments-ledger-ingestor:live'
data['event_source_arn'] = 'arn:aws:sqs:us-east-1:111122223333:payments-ledger-v2'
data['batch_size'] = 3
data['function_response_types'] = ['ReportBatchItemFailures']
mapping.write_text(json.dumps(data, indent=2) + '\n')
SOLVEPY
