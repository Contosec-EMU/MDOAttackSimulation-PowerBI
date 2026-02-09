#!/bin/bash
set -euo pipefail

# Install Python packages to persistent /home storage (survives restarts).
# Only runs on first boot or after package changes.
PACKAGES_DIR="/home/.python_packages/lib/site-packages"
MARKER="$PACKAGES_DIR/.installed_hash"
CURRENT_HASH=$(md5sum requirements.txt | cut -d' ' -f1)

if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$CURRENT_HASH" ]; then
    echo "Installing Python dependencies (first boot or requirements changed)..."
    pip install --target "$PACKAGES_DIR" -r requirements.txt \
        --no-cache-dir --quiet --default-timeout=120 --retries 3
    echo "$CURRENT_HASH" > "$MARKER"
    echo "Dependencies installed."
else
    echo "Dependencies already installed, skipping pip install."
fi

export PYTHONPATH="$PACKAGES_DIR:${PYTHONPATH:-}"
export PATH="$PACKAGES_DIR/bin:$PATH"
python -m streamlit run app.py \
    --server.port "${PORT:-8000}" \
    --server.address 0.0.0.0 \
    --server.headless true
