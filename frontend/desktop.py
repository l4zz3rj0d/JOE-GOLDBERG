# frontend/desktop.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import webview
import asyncio
import threading
import json
import re
from pathlib import Path
from core.orchestrator import Orchestrator
from core.target_model import Target
from core.case_brief import CaseBrief, parse_brief_with_slm
from narrative.joe_voice import JoeVoice
from narrative.session_memory import SessionMemory
from memory.lessons_store import LessonsStore

ROOT = Path(__file__).parent
HTML_PATH = ROOT / "app.html"

# Keywords that signal extra context beyond just the target
_CONTEXT_SIGNALS = re.compile(
    r"(work|employ|company|corp|repo|github|leak|old|suspect|ctf|"
    r"used to|might have|previously|formerly|known as)",
    re.IGNORECASE,
)


class JoeAPI:
    def __init__(self):
        self._window = None
        self._target: Target = None
        self._memory = SessionMemory()
        self._voice = JoeVoice()
        self._lessons_store = LessonsStore()
        self._orch = None
        self._stalk_loop = None
        self._stalk_task = None
        self._last_entity = None  # Track for false-positive command

    def set_window(self, window):
        self._window = window
        self._orch = Orchestrator(
            on_status=self._on_status,
            on_find=self._on_find,
            on_done=lambda t: self._on_done(t, aborted=False),
            lessons_store=self._lessons_store,
        )

    def stalk(self, target: str):
        print(f"\n[desktop] Starting investigation: {target}")
        self._memory.add("user", f"stalk {target}")
        threading.Thread(target=self._run_stalk, args=(target, None), daemon=True).start()

    def smart_stalk(self, text: str):
        print(f"\n[desktop] Analyzing intent: {text}")
        self._memory.add("user", text)
        threading.Thread(target=self._run_smart_stalk, args=(text,), daemon=True).start()

    def ask(self, question: str):
        self._memory.add("user", question)
        threading.Thread(target=self._run_ask, args=(question,), daemon=True).start()

    def false_positive(self, platform: str, context: str = "general"):
        """Record a false-positive lesson from the desktop UI."""
        if not platform and self._last_entity:
            platform = self._last_entity.platform

        if not platform:
            self._emit("error", {"message": "Which platform? Tell me what I got wrong."})
            return

        trigger = f"{platform} username profile claimed to exist but was a false positive"
        lesson = f"{platform} gives false positives — lower confidence for future hits on this platform"

        success = self._lessons_store.add_lesson(
            trigger=trigger,
            lesson=lesson,
            platform=platform,
            context=context,
        )

        if success:
            self._emit("joe_answer", {
                "text": f"Lesson learned about {platform}. I won't make that mistake again.",
                "rate_limited": False,
                "mode": "investigation" if self._target else "advisor",
            })
        else:
            self._emit("joe_answer", {
                "text": "I can't store lessons right now — memory modules aren't installed.",
                "rate_limited": False,
                "mode": "advisor",
            })

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

    def get_evidence_uri(self, relative_path: str) -> str:
        if not relative_path:
            return ""
        try:
            if relative_path.startswith("file://"):
                from urllib.parse import unquote, urlparse
                p_str = unquote(urlparse(relative_path).path)
                path = Path(p_str).resolve()
            else:
                p = Path(relative_path)
                if p.is_absolute():
                    path = p.resolve()
                else:
                    rel = relative_path.lstrip("./").lstrip("/")
                    path = (ROOT.parent / rel).resolve()

            if path.exists() and path.is_file():
                import base64
                import mimetypes
                
                mime, _ = mimetypes.guess_type(path)
                if not mime or not mime.startswith("image/"):
                    suffix = path.suffix.lower()
                    if suffix in (".jpg", ".jpeg"):
                        mime = "image/jpeg"
                    elif suffix == ".png":
                        mime = "image/png"
                    elif suffix == ".gif":
                        mime = "image/gif"
                    elif suffix == ".svg":
                        mime = "image/svg+xml"
                    elif suffix == ".webp":
                        mime = "image/webp"
                    else:
                        mime = "image/png"

                data = path.read_bytes()
                b64_str = base64.b64encode(data).decode("ascii")
                return f"data:{mime};base64,{b64_str}"
        except Exception:
            pass
        return ""

    def get_map_texture(self) -> str:
        texture_path = ROOT.parent / "assets" / "world_outline.jpg"
        if not texture_path.exists():
            texture_path = ROOT / "world_outline.jpg"
        if texture_path.exists():
            import base64
            data = texture_path.read_bytes()
            b64_str = base64.b64encode(data).decode("ascii")
            return f"data:image/jpeg;base64,{b64_str}"
        return ""

    def open_url(self, url: str):
        import webbrowser
        if url.startswith("cases/") or not url.startswith(("http://", "https://", "file://")):
            abs_path = (Path(__file__).parent.parent / url).resolve()
            if abs_path.exists():
                url = abs_path.as_uri()
        webbrowser.open(url)

    def _run_smart_stalk(self, text: str):
        # Deterministic check for target extraction
        match = re.match(r"^(stalk|pivot)\s+(\S+)", text, re.IGNORECASE)
        if match and match.group(2).lower() not in ("again", "them", "him", "her", "it", "to", "the", "me"):
            target_str = match.group(2)
        else:
            target_str = self._voice.extract_target(text, self._target)

        if not target_str or target_str.lower() == "none":
            self._emit("error", {"message": "Who do you want me to look into? I need a clear target."})
            return

        self._emit("scan_status", {"message": f"Target locked: {target_str}"})

        # Extract brief from context beyond the target
        # If the user typed "stalk johndoe — they worked at Acme Corp"
        # strip the stalk command and target, use the rest as brief
        brief = None
        remainder = text
        # Remove command prefix
        for prefix in ["stalk ", "pivot "]:
            if remainder.lower().startswith(prefix):
                remainder = remainder[len(prefix):]
                break
        # Remove the target string itself
        remainder = remainder.replace(target_str, "", 1).strip()
        # Strip common separators
        remainder = re.sub(r"^[\-—–,;:]+\s*", "", remainder).strip()

        if remainder and _CONTEXT_SIGNALS.search(remainder):
            self._emit("scan_status", {"message": "Parsing case brief from your context..."})
            brief = parse_brief_with_slm(remainder)
            if brief.hints:
                hints_summary = ", ".join(brief.hints.keys())
                self._emit("scan_status", {"message": f"Brief extracted: {hints_summary}"})

        self._emit("scan_status", {"message": "Spinning up background engines..."})
        self._run_stalk(target_str, brief)

    def _run_stalk(self, target: str, brief: CaseBrief = None):
        self._stalk_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._stalk_loop)
        self._stalk_task = self._stalk_loop.create_task(self._orch.stalk(target, brief=brief))
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
            "mode": result.get("mode", "advisor"),
            "error": result.get("error", False)
        })

    async def _on_status(self, msg: str):
        self._emit("scan_status", {"message": msg})

    async def _on_find(self, entity, target):
        self._target = target
        self._last_entity = entity  # Track for false-positive command
        
        is_verified = entity.metadata.get("verified")
        conf = entity.confidence
        
        # Real-time UI status emission (No per-finding SLM calls — single closing monologue runs at end)
        url_val = (
            entity.metadata.get("url", "")
            or entity.metadata.get("profile", "")
            or entity.metadata.get("source_url", "")
            or entity.metadata.get("link", "")
        )

        self._emit("entity_found", {
            "type": entity.entity_type,
            "value": entity.value,
            "platform": entity.platform or "",
            "confidence": conf,
            "url": url_val,
            "verified": is_verified,
            "quote": None,
            "should_narrate": False,
            "screenshot_path": entity.metadata.get("screenshot_path"),
            "avatar_path": entity.metadata.get("avatar_path"),
            "metadata": entity.metadata,
        })

    async def _on_done(self, target, aborted=False):
        self._target = target
        error = False
        if aborted:
            text = "Investigation aborted. You pulled me away. But I remember what we found so far."
            used_gemini = False
        else:
            result = self._voice.closing_monologue(target)
            text = result["text"]
            used_gemini = result.get("used_gemini", False)
            error = result.get("error", False)
            if result.get("rate_limited"):
                self._emit("rate_limited", {})

        self._memory.add("joe", text)
        self._emit("investigation_done", {
            "target": target.to_dict(),
            "monologue": text,
            "used_gemini": used_gemini,
            "error": error
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

        src_back = ROOT.parent / "assets" / "joegui.png"
        dst_back = ROOT / "joegui.png"
        if src_back.exists() and not dst_back.exists():
            shutil.copy(src_back, dst_back)

        src_geo = ROOT.parent / "assets" / "world_outline.jpg"
        dst_geo = ROOT / "world_outline.jpg"
        if src_geo.exists() and not dst_geo.exists():
            shutil.copy(src_geo, dst_geo)

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