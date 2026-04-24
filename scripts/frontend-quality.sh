#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/frontend"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

check_node() {
  if ! command -v node &>/dev/null; then
    echo "Error: Node.js is not installed." >&2
    exit 1
  fi
  if ! command -v npm &>/dev/null; then
    echo "Error: npm is not installed." >&2
    exit 1
  fi
}

ensure_deps() {
  if [ ! -d "$ROOT_DIR/node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install --prefix "$ROOT_DIR"
  fi
}

run_format_check() {
  echo "--- Prettier (format check) ---"
  npm run --prefix "$ROOT_DIR" format:check
  echo "Prettier: OK"
}

run_format_fix() {
  echo "--- Prettier (auto-format) ---"
  npm run --prefix "$ROOT_DIR" format
  echo "Prettier: files formatted"
}

run_lint() {
  echo "--- ESLint ---"
  npm run --prefix "$ROOT_DIR" lint
  echo "ESLint: OK"
}

run_lint_fix() {
  echo "--- ESLint (auto-fix) ---"
  npm run --prefix "$ROOT_DIR" lint:fix
  echo "ESLint: fixes applied"
}

usage() {
  cat <<EOF
Usage: $0 [--fix]

  (no args)  Check formatting and lint without modifying files.
  --fix      Auto-format with Prettier and apply ESLint auto-fixes.
EOF
}

main() {
  check_node
  ensure_deps

  if [[ "${1:-}" == "--fix" ]]; then
    run_format_fix
    run_lint_fix
    echo ""
    echo "All frontend quality fixes applied."
  elif [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
  else
    run_format_check
    run_lint
    echo ""
    echo "All frontend quality checks passed."
  fi
}

main "$@"
