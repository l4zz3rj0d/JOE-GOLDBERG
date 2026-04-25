# frontend/desktop.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import webview
import asyncio
import threading
import json
from pathlib import Path
from core.orchestrator import Orchestrator
from core.target_model import Target
from narrative.joe_voice import JoeVoice
from narrative.session_memory import SessionMemory

ROOT = Path(__file__).parent
HTML_PATH = ROOT / "app.html"


class JoeAPI:
    def __init__(self):
        self._window = None
        self._target: Target = None
        self._memory = SessionMemory()
        self._voice = JoeVoice()
        self._orch = None

    def set_window(self, window):
        self._window = window
        self._orch = Orchestrator(
            on_status=self._on_status,
            on_find=self._on_find,
            on_done=self._on_done,
        )

    def stalk(self, target: str):
        print(f"\n[desktop] Starting investigation: {target}")
        self._memory.add("user", f"stalk {target}")
        threading.Thread(target=self._run_stalk, args=(target,), daemon=True).start()

    def ask(self, question: str):
        print(f"\n[desktop] User asked: {question}")
        self._memory.add("user", question)
        threading.Thread(target=self._run_ask, args=(question,), daemon=True).start()

    def resume(self, target: str):
        try:
            self._target = Target.load(target)
            self._emit("resumed", self._target.to_dict())
        except FileNotFoundError:
            self._emit("error", {"message": f"No case found for: {target}"})

    def list_cases(self):
        from core.target_model import CASES_DIR
        cases = []
        for p in CASES_DIR.glob("*/case.json"):
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
        if self._target:
            self._target.notes.append(note)
            self._target.save()
            self._emit("note_saved", {"note": note})

    def export_report(self):
        if not self._target:
            return
        from exporters.html_report import generate
        path = generate(self._target)
        self._emit("report_ready", {"path": str(path)})

    def _run_stalk(self, target: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._orch.stalk(target))
        loop.close()

    def _run_ask(self, question: str):
        full_answer = ""
        print("[desktop] Starting stream...")
        
        # Use stream_chat instead of simple chat
        history = self._memory.last_n()
        if self._target:
            # Context-aware chat
            history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-6:])
            prompt = f"Investigation: {self._target.primary}\nRecent conversation:\n{history_text}\n\nUser asked: {question}"
        else:
            prompt = question

        for chunk in self._voice.stream_chat(prompt):
            full_answer += chunk
            self._emit("joe_stream", {"chunk": chunk})
        
        print(f"[desktop] Stream complete. Total length: {len(full_answer)} chars")
        self._memory.add("joe", full_answer)
        self._emit("joe_answer", {"text": full_answer})

    async def _on_status(self, msg: str):
        self._emit("scan_status", {"message": msg})

    async def _on_find(self, entity, target):
        self._target = target
        quote = self._voice.inline_quote(
            entity.entity_type, entity.value, entity.platform or ""
        )
        self._emit("entity_found", {
            "type": entity.entity_type,
            "value": entity.value,
            "platform": entity.platform or "",
            "confidence": entity.confidence,
            "quote": quote,
        })

    async def _on_done(self, target):
        self._target = target
        monologue = self._voice.closing_monologue(target)
        self._memory.add("joe", monologue)
        self._emit("investigation_done", {
            "target": target.to_dict(),
            "monologue": monologue,
        })

    def _emit(self, event: str, data: dict):
        if self._window:
            self._window.evaluate_js(
                f"window.joe && window.joe.receive('{event}', {json.dumps(data)})"
            )


class JoeDesktop:
    def launch(self):
        import shutil
        src = ROOT.parent / "assets" / "joe.jpeg"
        dst = ROOT / "joe.jpeg"
        if src.exists() and not dst.exists():
            shutil.copy(src, dst)

        api = JoeAPI()
        window = webview.create_window(
            title="Joe Goldberg",
            url=str(HTML_PATH),
            js_api=api,
            width=1200,
            height=780,
            min_size=(900, 600),
            background_color="#1a0505",
        )

        api.set_window(window)
        webview.start(debug=False)