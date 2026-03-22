#!/usr/bin/env python3
# joe.py
import sys
import os
from pathlib import Path

# CRITICAL — add project root to sys.path so all modules resolve
# regardless of where joe is called from
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now safe to import everything else
def boot_checks():
    issues = []
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            if not any("mistral" in m for m in models):
                issues.append("mistral:7b-instruct not pulled.\n  Run: ollama pull mistral:7b-instruct")
    except:
        issues.append("Ollama not running.\n  Run: ollama serve")

    if issues:
        print("\n[joe] Pre-flight issues:\n")
        for issue in issues:
            print(f"  ✗ {issue}\n")
        print("  Joe can still run — LLM features will be limited.\n")


def launch_cli(initial_target: str = None):
    from tui.joe_cli import run
    run(initial_target=initial_target)


def launch_desktop():
    try:
        import webview
        from frontend.desktop import JoeDesktop
        JoeDesktop().launch()
    except ImportError as e:
        print(f"[joe] Desktop unavailable: {e}")
        print("      Falling back to CLI...\n")
        launch_cli()
    except Exception as e:
        print(f"[joe] Desktop error: {e}")
        print("      Falling back to CLI...\n")
        launch_cli()


def main():
    args = sys.argv[1:]
    boot_checks()

    if "--cli" in args or "--tui" in args:
        launch_cli()
    elif args and args[0] == "stalk" and len(args) > 1:
        launch_cli(initial_target=args[1])
    elif args and args[0] == "resume" and len(args) > 1:
        from tui.joe_cli import JoeCLI
        cli = JoeCLI()
        cli._resume(args[1])
        cli._loop()
    elif args and args[0] in ("-h", "--help"):
        launch_cli()
    else:
        launch_desktop()


if __name__ == "__main__":
    main()