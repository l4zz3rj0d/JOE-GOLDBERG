# tui/joe_cli.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import threading
from pathlib import Path
from rich.console import Console
from core.orchestrator import Orchestrator
from core.target_model import Target, Entity
from narrative.joe_voice import JoeVoice
from narrative.session_memory import SessionMemory

console = Console()

C_GOLD   = "#e8a020"
C_RED    = "#e63b1f"
C_LIGHT  = "#f0dcc8"
C_GREEN  = "#3aad50"
C_ORANGE = "#e05520"
C_DIM    = "#9a8070"
C_ACCENT = "#ff4422"

BANNER = r"""
     ██╗ ██████╗ ███████╗
     ██║██╔═══██╗██╔════╝
     ██║██║   ██║█████╗
██   ██║██║   ██║██╔══╝
╚█████╔╝╚██████╔╝███████╗
 ╚════╝  ╚═════╝ ╚══════╝

 ██████╗  ██████╗ ██╗     ██████╗ ██████╗ ███████╗██████╗  ██████╗
██╔════╝ ██╔═══██╗██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔════╝
██║  ███╗██║   ██║██║     ██║  ██║██████╔╝█████╗  ██████╔╝██║  ███╗
██║   ██║██║   ██║██║     ██║  ██║██╔══██╗██╔══╝  ██╔══██╗██║   ██║
╚██████╔╝╚██████╔╝███████╗██████╔╝██████╔╝███████╗██║  ██║╚██████╔╝
 ╚═════╝  ╚═════╝ ╚══════╝╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝
"""


def print_banner():
    console.print()
    for line in BANNER.splitlines():
        console.print(f"  [bold {C_ACCENT}]{line}[/]")
    console.print()
    console.print(f'  [{C_GOLD}]  "I notice everything."[/]')
    console.print(f'  [{C_DIM}]  OSINT Investigator — zero APIs, fully local[/]')
    console.print()
    console.print(f"  [{C_DIM}]  stalk · resume · cases · pivot · notes · export · help · exit[/]")
    console.print()


def print_status(msg: str):
    console.print(f"  [{C_DIM}]  ›  {msg}[/]")


def print_found(entity: Entity):
    plat = f"  [{C_GREEN}]{entity.platform}[/]" if entity.platform else ""
    console.print(
        f"  [{C_GREEN}]  ✓[/]  [bold {C_LIGHT}]{entity.value}[/]{plat}"
    )


def print_breach(entity: Entity):
    plat = f"  [{C_ORANGE}]{entity.platform}[/]" if entity.platform else ""
    console.print(
        f"  [{C_ORANGE}]  ⚠[/]  [bold {C_ORANGE}]{entity.value}[/]{plat}"
    )


def print_joe_quote(quote: str):
    if not quote.strip():
        return
    console.print()
    for line in quote.strip().splitlines():
        console.print(f"       [{C_GOLD}]│  {line}[/]")
    console.print()


def print_findings(target: Target):
    console.print()
    console.print(f"  [{C_ACCENT}]  {'─' * 58}[/]")
    console.print(f"  [bold {C_LIGHT}]  FINDINGS[/]")
    console.print(f"  [{C_ACCENT}]  {'─' * 58}[/]")
    console.print()

    for e in target.entities:
        plat = f"  [{C_DIM}]({e.platform})[/]" if e.platform else ""
        console.print(
            f"  [{C_DIM}]  {e.entity_type:<16}[/]"
            f"[{C_LIGHT}]{e.value}[/]{plat}"
        )

    if target.breaches:
        console.print()
        for b in target.breaches:
            fields = ", ".join(b.exposed_fields[:3])
            console.print(
                f"  [{C_ORANGE}]  {'breach':<16}[/]"
                f"[bold {C_ORANGE}]{b.name}[/]"
                f"  [{C_DIM}]{b.date}  {fields}[/]"
            )

    console.print()
    filled = int(target.risk_score * 30)
    bar = (
        f"[{C_ACCENT}]{'█' * filled}[/]"
        f"[{C_DIM}]{'░' * (30 - filled)}[/]"
    )
    console.print(
        f"  [{C_DIM}]  {'risk score':<16}[/]{bar}  "
        f"[bold {C_ACCENT}]{target.risk_score:.2f}[/]"
    )
    console.print()
    console.print(f"  [{C_ACCENT}]  {'─' * 58}[/]")
    console.print()


def print_monologue(text: str):
    from rich.text import Text
    from rich.padding import Padding

    console.print()
    console.print(f"  [{C_ACCENT}]  ┌─ joe {'─' * 46}[/]")
    console.print()

    for line in text.strip().splitlines():
        if line.strip():
            # Wrap long lines cleanly at 70 chars
            words = line.split()
            current = ""
            for word in words:
                if len(current) + len(word) + 1 > 70:
                    console.print(f"  [{C_GOLD}]  {current}[/]")
                    current = word
                else:
                    current = f"{current} {word}".strip()
            if current:
                console.print(f"  [{C_GOLD}]  {current}[/]")
        else:
            console.print()

    console.print()
    console.print(f"  [{C_ACCENT}]  └{'─' * 50}[/]")
    console.print()


def show_help():
    console.print()
    console.print(f"  [bold {C_LIGHT}]  COMMANDS[/]")
    console.print()
    for cmd, desc in [
        ("stalk  <target>",  "start new investigation (email, domain, IP, username)"),
        ("resume <target>",  "load and continue a saved case"),
        ("pivot  <entity>",  "investigate a newly discovered entity"),
        ("cases",            "list all saved investigations"),
        ("notes  <text>",    "add a note to the current case"),
        ("export",           "export current case as HTML report"),
        ("help",             "show this"),
        ("exit",             "leave"),
    ]:
        console.print(
            f"  [bold {C_ACCENT}]  {cmd:<26}[/][{C_DIM}]{desc}[/]"
        )
    console.print(
        f"\n  [{C_DIM}]  Or type anything — Joe will answer from investigation context.[/]\n"
    )


def list_cases():
    cases = list(CASES_DIR.glob("*/case.json"))
    if not cases:
        console.print(f"\n  [{C_DIM}]  No saved cases yet.[/]\n")
        return
    console.print()
    for p in cases:
        console.print(f"  [{C_ACCENT}]  ·[/]  [{C_LIGHT}]{p.parent.name}[/]")
    console.print()


def get_prompt() -> str:
    try:
        sys.stdout.write("\033[38;2;230;59;31m  joe ›\033[0m  ")
        sys.stdout.flush()
        return input().strip()
    except (EOFError, KeyboardInterrupt):
        console.print(f'\n\n  [{C_GOLD}]  "Everyone leaves eventually."[/]\n')
        sys.exit(0)


class JoeCLI:
    def __init__(self, initial_target: str = None):
        self.initial_target = initial_target
        self.current_target: Target = None
        self.voice = JoeVoice()
        self.memory = SessionMemory()
        self.orch = Orchestrator(
            on_status=self._on_status,
            on_find=self._on_find,
            on_done=self._on_done,
        )

    def run(self):
        print_banner()
        if self.initial_target:
            self._stalk(self.initial_target)
        self._loop()

    def _loop(self):
        while True:
            text = get_prompt()
            if not text:
                continue
            parts = text.split(" ", 1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("exit", "quit", "q"):
                console.print(f'\n  [{C_GOLD}]  "I\'ll always be watching."[/]\n')
                sys.exit(0)
            elif cmd == "stalk" and arg:
                self._stalk(arg)
            elif cmd == "pivot" and arg:
                self._stalk(arg)
            elif cmd == "resume" and arg:
                self._resume(arg)
            elif cmd == "cases":
                list_cases()
            elif cmd == "notes" and arg and self.current_target:
                self.current_target.notes.append(arg)
                self.current_target.save()
                console.print(f"\n  [{C_GREEN}]  Note saved.[/]\n")
            elif cmd == "export" and self.current_target:
                self._export()
            elif cmd == "help":
                show_help()
            else:
                self._ask(text)

    def _stalk(self, target: str):
        console.print()
        console.print(f"  [{C_ACCENT}]  ── investigating: [bold]{target}[/bold] ──[/]")
        console.print()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.current_target = loop.run_until_complete(
                self.orch.stalk(target)
            )
            loop.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join()

    def _resume(self, target: str):
        try:
            self.current_target = Target.load(target)
            console.print(f"\n  [{C_GREEN}]  Resumed: {target}[/]\n")
        except FileNotFoundError:
            console.print(f"\n  [{C_ORANGE}]  No case found for: {target}[/]\n")

    def _ask(self, question: str):
        if not self.current_target or not self.current_target.entities:
            console.print(f"\n  [{C_DIM}]  thinking...[/]")
            result = self.voice.chat(question, None)
        else:
            console.print(f"\n  [{C_DIM}]  thinking...[/]")
            result = self.voice.chat(question, self.current_target)

        self.memory.add("user", question)
        self.memory.add("joe", result["text"])

        if result.get("rate_limited"):
            console.print(f"\n  [{C_ORANGE}]  ⚠ Rate limited — using local SLM[/]")

        print_monologue(result["text"])

    def _export(self):
        from exporters.html_report import generate
        path = generate(self.current_target)
        console.print(f"\n  [{C_GREEN}]  Report saved: {path}[/]\n")

    async def _on_status(self, msg: str):
        print_status(msg)

    async def _on_find(self, entity: Entity, target: Target):
        if entity.entity_type == "breach":
            print_breach(entity)
        else:
            print_found(entity)
        quote = self.voice.inline_quote(
            entity.entity_type,
            entity.value,
            entity.platform or "",
        )
        if quote:
            print_joe_quote(quote)

    async def _on_done(self, target: Target):
        print_findings(target)
        console.print(f"  [{C_DIM}]  composing...[/]")
        result = self.voice.closing_monologue(target)
        if result.get("rate_limited"):
            console.print(f"  [{C_ORANGE}]  ⚠ Gemini rate limited — using local SLM for monologue[/]")
        self.memory.add("joe", result["text"])
        print_monologue(result["text"])


def run(initial_target: str = None):
    JoeCLI(initial_target=initial_target).run()