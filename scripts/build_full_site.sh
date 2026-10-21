#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBSITE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_DIR="$(cd "${WEBSITE_DIR}/.." && pwd)"

MKDOCS_BIN="mkdocs"
if ! command -v "${MKDOCS_BIN}" >/dev/null 2>&1; then
  if [[ -x "${WORKSPACE_DIR}/venv/bin/mkdocs" ]]; then
    MKDOCS_BIN="${WORKSPACE_DIR}/venv/bin/mkdocs"
  elif [[ -x "${WEBSITE_DIR}/.venv/bin/mkdocs" ]]; then
    MKDOCS_BIN="${WEBSITE_DIR}/.venv/bin/mkdocs"
  else
    echo "Error: mkdocs binary not found in PATH or venv." >&2
    exit 1
  fi
fi

echo "[1/3] Building MkDocs site (--strict)..."
cd "${WEBSITE_DIR}"
"${MKDOCS_BIN}" build --strict

if [[ -d "${WORKSPACE_DIR}/impulse-graph-java" ]] && command -v mvn >/dev/null 2>&1; then
  echo "[2/3] Generating aggregated Javadocs from impulse-graph-java..."
  (
    cd "${WORKSPACE_DIR}/impulse-graph-java"
    mvn javadoc:aggregate -DskipTests -B -q
  )
  mkdir -p "${WEBSITE_DIR}/site/javadoc"
  cp -R "${WORKSPACE_DIR}/impulse-graph-java/target/site/apidocs/"* "${WEBSITE_DIR}/site/javadoc/"
  echo "      Copied Javadocs to ${WEBSITE_DIR}/site/javadoc/"
else
  echo "[2/3] Skipping Javadoc generation (impulse-graph-java or mvn not available)."
fi

if [[ -f "${WORKSPACE_DIR}/impulse-graph-core/impulse-cpp/Doxyfile" ]] && command -v doxygen >/dev/null 2>&1; then
  echo "[3/3] Generating C-ABI & C++20 Doxygen HTML from impulse-graph-core..."
  (
    cd "${WORKSPACE_DIR}/impulse-graph-core/impulse-cpp"
    doxygen Doxyfile
  )
  mkdir -p "${WEBSITE_DIR}/site/doxygen"
  cp -R "${WORKSPACE_DIR}/impulse-graph-core/impulse-cpp/build/docs/html/"* "${WEBSITE_DIR}/site/doxygen/"
  echo "      Copied Doxygen HTML to ${WEBSITE_DIR}/site/doxygen/"
else
  echo "[3/3] Skipping Doxygen HTML generation (doxygen not installed locally; generated in CI)."
fi

echo "[+] Full documentation site built at: ${WEBSITE_DIR}/site"
