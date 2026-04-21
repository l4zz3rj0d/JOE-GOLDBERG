#!/bin/bash
set -e

echo ""
echo "  installing joe goldberg..."
echo ""

# ── Python deps ───────────────────────────────────────────────
pip install -e . --quiet
pip install sherlock-project maigret --quiet

# ── Ollama ────────────────────────────────────────────────────
if ! command -v ollama &> /dev/null; then
    echo "  installing ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Start ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    echo "  starting ollama..."
    ollama serve &>/dev/null &
    sleep 3
fi

# ── Pull model ────────────────────────────────────────────────
if ! ollama list 2>/dev/null | grep -q "llama3.2:3b"; then
    echo "  pulling llama3.2:3b (fast local fallback)..."
    ollama pull llama3.2:3b
fi

# ── System command ────────────────────────────────────────────
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_ACTIVATE="$(find "$INSTALL_DIR" -name activate -path "*/bin/activate" 2>/dev/null | head -1)"

echo "  registering joe as system command..."

sudo bash -c "cat > /usr/local/bin/joe << 'WRAPPER'
#!/bin/bash
$([ -n "$VENV_ACTIVATE" ] && echo "source $VENV_ACTIVATE")
cd $INSTALL_DIR
python $INSTALL_DIR/joe.py \"\$@\"
WRAPPER"

sudo chmod +x /usr/local/bin/joe

# ── Desktop entry ─────────────────────────────────────────────
echo "  creating desktop entry..."

ICON_PATH="$INSTALL_DIR/assets/joe.jpeg"

# Convert to PNG if imagemagick available — better icon support
if command -v convert &> /dev/null; then
    convert "$ICON_PATH" "$INSTALL_DIR/assets/joe-icon.png" 2>/dev/null && \
    ICON_PATH="$INSTALL_DIR/assets/joe-icon.png"
fi

mkdir -p ~/.local/share/applications

cat > ~/.local/share/applications/joe-goldberg.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Joe Goldberg
GenericName=OSINT Investigator
Comment=Autonomous OSINT Investigator — zero APIs, fully local
Exec=bash -c "source $VENV_ACTIVATE && cd $INSTALL_DIR && python $INSTALL_DIR/joe.py"
Icon=$ICON_PATH
Terminal=false
Categories=Security;Network;
Keywords=osint;recon;investigation;security;pentest;
StartupNotify=true
StartupWMClass=Joe Goldberg
EOF

chmod +x ~/.local/share/applications/joe-goldberg.desktop

# Refresh GNOME app grid
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications/ 2>/dev/null
fi

# Try to refresh GNOME shell if running
if command -v xdg-desktop-menu &> /dev/null; then
    xdg-desktop-menu forceupdate 2>/dev/null
fi

# ── Ollama autostart on login ─────────────────────────────────
echo "  configuring ollama autostart..."

mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/ollama.service << EOF
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ollama serve
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user enable ollama.service 2>/dev/null
systemctl --user start ollama.service 2>/dev/null

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "  ✓ joe installed"
echo "  ✓ system command registered — run: joe"
echo "  ✓ desktop icon created — search 'Joe Goldberg' in app grid"
echo "  ✓ ollama configured to start automatically on login"
echo ""
echo "  ─────────────────────────────────────────────────────────"
echo "  Gemini API key setup  (free key at https://aistudio.google.com/apikey)"
echo "  ─────────────────────────────────────────────────────────"
echo ""

# Detect the user's login shell and print the right config command
USER_SHELL="$(basename "$(getent passwd "$USER" | cut -d: -f7 2>/dev/null || echo "${SHELL:-bash}")")"

case "$USER_SHELL" in
  zsh)
    echo "  Your shell: zsh"
    echo ""
    echo "  echo 'export GEMINI_API_KEY=\"your_key_here\"' >> ~/.zshrc"
    echo "  source ~/.zshrc"
    echo ""
    echo "  (if you see shopt errors, remove any 'source ~/.bashrc' line from ~/.zshrc)"
    ;;
  fish)
    echo "  Your shell: fish"
    echo ""
    echo "  set -Ux GEMINI_API_KEY \"your_key_here\""
    ;;
  *)
    echo "  Your shell: bash / other"
    echo ""
    echo "  echo 'export GEMINI_API_KEY=\"your_key_here\"' >> ~/.bashrc"
    echo "  source ~/.bashrc"
    ;;
esac

echo ""
echo "  To make narration work from the desktop icon too, also set:"
echo "  sudo nano /usr/local/bin/joe"
echo "  Add: export GEMINI_API_KEY=\"your_key_here\" (below the shebang)"
echo ""