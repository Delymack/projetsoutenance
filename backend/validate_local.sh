#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs/local-validation"
mkdir -p "$LOG_DIR"

VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"
PIP_BIN="${PIP_BIN:-$VENV_DIR/bin/pip}"

if [ ! -f "$ROOT_DIR/manage.py" ]; then
  echo "[ERROR] manage.py not found in $ROOT_DIR"
  exit 1
fi

if [ ! -f "$ROOT_DIR/requirements.txt" ]; then
  echo "[ERROR] requirements.txt not found in $ROOT_DIR"
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[INFO] Creating virtual environment in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[ERROR] Python virtual environment could not be created: $VENV_DIR"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[ERROR] Virtual environment directory missing: $VENV_DIR"
  exit 1
fi

# Upgrade pip first, then install project dependencies.
"$PYTHON_BIN" -m pip install --upgrade pip >/dev/null
"$PYTHON_BIN" -m pip install -r "$ROOT_DIR/requirements.txt" 2>&1 | tee "$LOG_DIR/pip-install.log"

echo "[INFO] Running Django system check"
"$PYTHON_BIN" "$ROOT_DIR/manage.py" check 2>&1 | tee "$LOG_DIR/check.log"

echo "[INFO] Applying database migrations"
"$PYTHON_BIN" "$ROOT_DIR/manage.py" migrate --noinput 2>&1 | tee "$LOG_DIR/migrate.log"

echo "[INFO] Running targeted Django tests"
"$PYTHON_BIN" "$ROOT_DIR/manage.py" test \
  tests.test_produits \
  tests.test_parametres_utilisateurs \
  tests.test_documents_impression \
  tests.test_promotions \
  2>&1 | tee "$LOG_DIR/tests_targeted.log"

echo "[INFO] Validation completed successfully."
echo "[INFO] Logs saved in: $LOG_DIR"
