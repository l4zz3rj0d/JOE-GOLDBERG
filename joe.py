#!/usr/bin/env python3
# joe.py — Joe Goldberg OSINT Tool
# Entry point: detects CLI vs desktop mode and boots accordingly

import sys
import os
import subprocess
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Ensure case + asset dirs exist ───────────────────────────
for d in ["cases", "assets", "logs"]:
    (ROOT / d).mkdir(exist_ok=True)


def check_ollama() -> bool:
    """Check if Ollama is running locally."""
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except:
        return False


def check_model(model: str = "mistral:7b-instruct") -> bool:
    """Check if the required model is pulled."""
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        return any(model in m for m in models)
    except:
        return False


def boot_checks():
    """Run pre-flight checks before launching."""
    issues = []

    if not check_ollama():
        issues.append(
            "  Ollama is not running.\n"
            "  Start it with: ollama serve"
        )
    elif not check_model():
        issues.append(
            "  mistral:7b-instruct not found.\n"
            "  Pull it with: ollama pull mistral:7b-instruct"
        )

    if issues:
        print("\n[joe] Pre-flight issues detected:\n")
        for issue in issues:
            print(f"  ✗ {issue}\n")
        print("  Joe can still run — LLM features will be limited.\n")


def launch_desktop():
    """Launch the PyWebView desktop application."""
    try:
        from frontend.desktop import JoeDesktop
        app = JoeDesktop()
        app.launch()
    except ImportError:
        print("[joe] pywebview not installed.")
        print("      pip install pywebview")
        print("      Falling back to CLI mode...\n")
        launch_cli()


def launch_cli(initial_target: str = None):
    from tui.joe_cli import run
    run(initial_target=initial_target)

def main():
    args = sys.argv[1:]

    # ── Run boot checks ───────────────────────────────────────
    boot_checks()

    # ── Routing logic ─────────────────────────────────────────

    # Force CLI/TUI mode
    if "--cli" in args or "--tui" in args:
        launch_cli()

    # Direct stalk from terminal: python joe.py stalk target
    elif len(args) >= 2 and args[0] == "stalk":
        launch_cli(initial_target=args[1])

    # Resume a case from terminal: python joe.py resume target
    elif len(args) >= 2 and args[0] == "resume":
        from tui.joe_tui import JoeApp
        JoeApp(resume_target=args[1]).run()

    # No args = desktop app
    else:
        launch_desktop()


if __name__ == "__main__":
    main()