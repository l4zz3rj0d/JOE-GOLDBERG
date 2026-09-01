#!/usr/bin/env python3
# soldierboy.py
import sys
import os
from pathlib import Path

# CRITICAL — add project root to sys.path so all modules resolve
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# If running inside 'point-break' environment which lacks GTK bindings, switch to system python3
if "point-break" in sys.executable and os.path.exists("/usr/bin/python3") and "SOLDIERBOY_SYS_EXEC" not in os.environ:
    os.environ["SOLDIERBOY_SYS_EXEC"] = "1"
    os.execv("/usr/bin/python3", ["/usr/bin/python3"] + sys.argv)

# Now safe to import everything else
def boot_checks():
    issues = []
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            if not models:
                issues.append("No local Ollama models pulled.\n  Run: ollama pull <model> (e.g., llama3.2:3b, qwen2.5:3b, gemma2:2b)")
    except Exception:
        issues.append("Ollama not running.\n  Run: ollama serve")

    if issues:
        print("\n[soldierboy] Pre-flight notice:\n")
        for issue in issues:
            print(f"  ⓘ {issue}\n")
        print("  Soldier Boy can still run using Cloud APIs (NVIDIA NIM / Gemini) or your configured local model.\n")


def launch_cli(initial_target: str = None):
    from tui.soldierboy_cli import run
    run(initial_target=initial_target)


def launch_desktop():
    try:
        import webview
        from frontend.desktop import SoldierBoyDesktop
        SoldierBoyDesktop().launch()
    except ImportError as e:
        print(f"[soldierboy] Desktop unavailable: {e}")
        print("      Falling back to CLI...\n")
        launch_cli()
    except Exception as e:
        print(f"[soldierboy] Desktop error: {e}")
        print("      Falling back to CLI...\n")
        launch_cli()


def main():
    args = sys.argv[1:]
    boot_checks()

    if "--cli" in args or "--tui" in args:
        launch_cli()
    elif args and args[0] in ("investigate", "stalk") and len(args) > 1:
        launch_cli(initial_target=args[1])
    elif args and args[0] == "resume" and len(args) > 1:
        from tui.soldierboy_cli import SoldierBoyCLI
        cli = SoldierBoyCLI()
        cli._resume(args[1])
        cli._loop()
    elif args and args[0] in ("-h", "--help"):
        launch_cli()
    else:
        launch_desktop()


if __name__ == "__main__":
    main()