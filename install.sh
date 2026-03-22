#!/bin/bash
set -e

echo ""
echo "  installing joe..."
echo ""

# Python deps
pip install -e . --quiet
pip install sherlock-project maigret --quiet

# Ollama — install if missing
if ! command -v ollama &> /dev/null; then
    echo "  installing ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Start ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &>/dev/null &
    sleep 2
fi

# Pull model only if not already downloaded
if ollama list 2>/dev/null | grep -q "mistral"; then
    echo "  mistral already downloaded — skipping."
else
    echo "  pulling mistral:7b-instruct (~4GB, one time only)..."
    ollama pull mistral:7b-instruct
fi

echo ""
echo "  done. run: joe"
echo ""