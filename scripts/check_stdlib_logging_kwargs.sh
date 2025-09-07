#!/usr/bin/env bash
set -euo pipefail

# Guard: flag stdlib logging calls that pass stray keyword args directly.
# Heuristic: only scan files that import stdlib logging; allowlist known kwargs.

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
cd "$ROOT_DIR"

TARGET_DIRS=(core api services strategies)

# Collect python files that import stdlib logging
mapfile -t FILES < <(rg -n --glob "*.py" --no-messages -l "^\s*import\s+logging\b|^\s*from\s+logging\b" ${TARGET_DIRS[@]})

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No Python files importing stdlib logging found in target dirs."
  exit 0
fi

OFFENSES=()
for f in "${FILES[@]}"; do
  # Skip generated/docs/examples/tests
  if [[ "$f" == tests/* ]] || [[ "$f" == examples/* ]] || [[ "$f" == docs/* ]]; then
    continue
  fi
  # Search for logger.<level>(..., some_kw=...) excluding allowed kwargs
  if rg --pcre2 -n "logger\.(debug|info|warning|error|critical)\([^)]*\b(?!extra|exc_info|stack_info|stacklevel)[a-zA-Z_]\w*\s*=" "$f" > /tmp/ci_logging_scan.out 2>/dev/null; then
    while IFS= read -r line; do
      OFFENSES+=("$f:$line")
    done < /tmp/ci_logging_scan.out
  fi
done

if [ ${#OFFENSES[@]} -gt 0 ]; then
  echo "Found potential stdlib logging misuse (kwargs passed directly):"
  printf '%s\n' "${OFFENSES[@]}"
  echo
  echo "Hint: Use extra={...} or switch to structlog channel loggers."
  exit 1
fi

echo "Stdlib logging kwargs check passed."
exit 0

