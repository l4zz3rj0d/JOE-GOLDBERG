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
        self._stalk_loop = None
        self._stalk_task = None

    def set_window(self, window):
        self._window = window
        self._orch = Orchestrator(
            on_status=self._on_status,
            on_find=self._on_find,
            on_done=lambda t: self._on_done(t, aborted=False),
        )

    def stalk(self, target: str):
        print(f"\n[desktop] Starting investigation: {target}")
        self._memory.add("user", f"stalk {target}")
        threading.Thread(target=self._run_stalk, args=(target,), daemon=True).start()

    def smart_stalk(self, text: str):
        print(f"\n[desktop] Analyzing intent: {text}")
        self._memory.add("user", text)
        threading.Thread(target=self._run_smart_stalk, args=(text,), daemon=True).start()

    def ask(self, question: str):
        self._memory.add("user", question)
        threading.Thread(target=self._run_ask, args=(question,), daemon=True).start()

    def get_model_info(self):
        model = self._voice.slm_model
        using_gemini = self._voice.gemini_available and not self._voice.gemini_rate_limited
        self._emit("model_info", {"model": model, "using_gemini": using_gemini})

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

    def open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    def _run_smart_stalk(self, text: str):
        target_str = self._voice.extract_target(text, self._target)
        if not target_str or target_str.lower() == "none":
            self._emit("error", {"message": "Who do you want me to look into? I need a clear target."})
            return
        
        self._emit("scan_status", {"message": f"Target locked: {target_str}"})
        self._emit("scan_status", {"message": "Spinning up background engines..."})
        self._run_stalk(target_str)

    def _run_stalk(self, target: str):
        self._stalk_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._stalk_loop)
        self._stalk_task = self._stalk_loop.create_task(self._orch.stalk(target))
        try:
            self._stalk_loop.run_until_complete(self._stalk_task)
        except asyncio.CancelledError:
            print("[desktop] Investigation cancelled by user.")
            if self._target:
                self._target.save()
                self._stalk_loop.run_until_complete(self._on_done(self._target, aborted=True))
            else:
                self._emit("error", {"message": "Investigation aborted before any data was gathered."})
        except Exception as e:
            print(f"[desktop] Error in stalk: {e}")
            self._emit("error", {"message": f"I hit an error: {str(e)}"})
        finally:
            self._stalk_loop.close()
            self._stalk_loop = None
            self._stalk_task = None

    def stop(self):
        if self._stalk_task and self._stalk_loop:
            self._stalk_loop.call_soon_threadsafe(self._stalk_task.cancel)

    def _run_ask(self, question: str):
        result = self._voice.chat(question, self._target)
        if result.get("rate_limited"):
            self._emit("rate_limited", {})
        self._emit("joe_answer", {
            "text": result["text"],
            "rate_limited": result.get("rate_limited", False),
            "mode": result.get("mode", "advisor")
        })

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
            "url": entity.metadata.get("url", ""),
            "quote": quote,
        })

    async def _on_done(self, target, aborted=False):
        self._target = target
        if aborted:
            text = "Investigation aborted. You pulled me away. But I remember what we found so far."
            used_gemini = False
        else:
            result = self._voice.closing_monologue(target)
            text = result["text"]
            used_gemini = result.get("used_gemini", False)
            if result.get("rate_limited"):
                self._emit("rate_limited", {})
        
        self._memory.add("joe", text)
        self._emit("investigation_done", {
            "target": target.to_dict(),
            "monologue": text,
            "used_gemini": used_gemini,
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