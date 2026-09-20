#!/usr/bin/env bash
# Resolve collect workflow flags. Sourced or executed with env:
#   COLLECTOR_ENABLED, AUTO_PR_ENABLED, EVENT_NAME, INPUT_DRY
# Prints KEY=value lines: collector, auto_pr, dry_run, skip
set -euo pipefail

collector=false
if [[ "${COLLECTOR_ENABLED:-}" == "true" ]]; then collector=true; fi
auto_pr=false
if [[ "${AUTO_PR_ENABLED:-}" == "true" ]]; then auto_pr=true; fi

# schedule: never treat missing inputs as write; only collector=true runs write path
# workflow_dispatch: dry_run input is boolean → GitHub passes 'true'/'false' strings
dry_run=true
if [[ "${EVENT_NAME}" == "workflow_dispatch" && "${INPUT_DRY}" == "false" ]]; then
  dry_run=false
fi
if [[ "${EVENT_NAME}" == "schedule" && "${collector}" == "true" ]]; then
  dry_run=false
fi

skip=false
if [[ "${EVENT_NAME}" == "schedule" && "${collector}" != "true" ]]; then
  skip=true
  dry_run=true
fi

echo "collector=${collector}"
echo "auto_pr=${auto_pr}"
echo "dry_run=${dry_run}"
echo "skip=${skip}"
