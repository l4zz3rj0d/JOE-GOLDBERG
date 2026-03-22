# PyWebView desktop launcher + API bridge
# Python functions exposed here are callable from JS as window.pywebview.api.*

import webview
import asyncio
import threading
import json
from pathlib import Path
from core.orchestrator import Orchestrator
from core.target_model import Target
from core.input_parser import parse
from narrative.joe_voice import JoeVoice
from narrative.session_memory import SessionMemory

ROOT = Path(__file__).parent
HTML_PATH = ROOT / "app.html"


class JoeAPI:
    """
    All methods here are exposed to JavaScript as:
        window.pywebview.api.method_name(args)
    JS calls Python. Python calls back via window.joe.receive(event, data).
    """

    def __init__(self, window_ref):
        self._window = window_ref
        self._loop = asyncio.new_event_loop()
        self._target: Target = None
        self._memory = SessionMemory()
        self._voice = JoeVoice()
        self._orch = Orchestrator(
            on_status=self._on_status,
            on_find=self._on_find,
            on_done=self._on_done,
        )

    # ── Called from JS ────────────────────────────────────────

    def stalk(self, target: str):
        """JS: window.pywebview.api.stalk('john@example.com')"""
        self._memory.add("user", f"stalk {target}")
        threading.Thread(
            target=self._run_stalk,
            args=(target,),
            daemon=True
        ).start()

    def ask(self, question: str):
        """JS: window.pywebview.api.ask('what about the outlook email?')"""
        self._memory.add("user", question)
        threading.Thread(
            target=self._run_ask,
            args=(question,),
            daemon=True
        ).start()

    def resume(self, target: str):
        """JS: window.pywebview.api.resume('john_doe_gmail_com')"""
        try:
            self._target = Target.load(target)
            self._emit("resumed", self._target.to_dict())
        except FileNotFoundError:
            self._emit("error", {"message": f"No case found for: {target}"})

    def list_cases(self):
        """JS: window.pywebview.api.list_cases()"""
        cases = []
        for p in Path("cases").glob("*/case.json"):
            try:
                data = json.loads(p.read_text())
                cases.append({
                    "slug": p.parent.name,
                    "primary": data["primary"],
                    "target_type": data["target_type"],
                    "risk_score": data["risk_score"],
                    "breaches": len(data["breaches"]),
                    "entities": len(data["entities"]),
                    "last_updated": data["last_updated"],
                })
            except:
                pass
        self._emit("cases_loaded", {"cases": cases})

    def add_note(self, note: str):
        """JS: window.pywebview.api.add_note('this email is suspicious')"""
        if self._target:
            self._target.notes.append(note)
            self._target.save()
            self._emit("note_saved", {"note": note})

    def export_report(self):
        """JS: window.pywebview.api.export_report()"""
        if not self._target:
            return
        from exporters.html_report import generate
        path = generate(self._target)
        self._emit("report_ready", {"path": str(path)})

    # ── Internal ──────────────────────────────────────────────

    def _run_stalk(self, target: str):
        """Run investigation in a background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._orch.stalk(target))
        loop.close()

    def _run_ask(self, question: str):
        """Answer a follow-up question in background thread."""
        if not self._target:
            self._emit("joe_answer", {"text": "No active investigation."})
            return
        answer = self._voice.answer(
            question, self._target, self._memory.last_n()
        )
        self._memory.add("joe", answer)
        self._emit("joe_answer", {"text": answer})

    async def _on_status(self, msg: str):
        self._emit("scan_status", {"message": msg})

    async def _on_find(self, entity, target):
        self._target = target
        # Get Joe's inline quote for this finding
        quote = self._voice.inline_quote(
            entity.entity_type,
            entity.value,
            entity.platform or "",
        )
        self._emit("entity_found", {
            "type":       entity.entity_type,
            "value":      entity.value,
            "platform":   entity.platform or "",
            "confidence": entity.confidence,
            "quote":      quote,
        })

    async def _on_done(self, target):
        self._target = target
        monologue = self._voice.closing_monologue(target)
        self._memory.add("joe", monologue)
        self._emit("investigation_done", {
            "target":     target.to_dict(),
            "monologue":  monologue,
        })

    def _emit(self, event: str, data: dict):
        """Send event from Python → JavaScript."""
        payload = json.dumps(data).replace("'", r"\'")
        self._window.evaluate_js(
            f"window.joe.receive('{event}', {payload})"
        )


class JoeDesktop:
    def launch(self):
        window = webview.create_window(
            title="Joe Goldberg",
            url=str(HTML_PATH),
            width=1200,
            height=780,
            min_size=(900, 600),
            background_color="#f5f0e5",
            frameless=False,
            easy_drag=False,
        )
        api = JoeAPI(window)
        webview.start(
            func=lambda: window.expose(api),
            debug=False,
        )