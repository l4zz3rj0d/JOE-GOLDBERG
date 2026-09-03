# frontend/desktop.py
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

import webview
import asyncio
import threading
import queue
import json
import re
import subprocess
import time
import os
import struct
import wave
# Suppress C-level ALSA / JACK warning log spam in terminal
try:
    from ctypes import CFUNCTYPE, c_char_p, c_int, cdll
    _ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
    def _py_error_handler(filename, line, function, err, fmt):
        pass
    _c_error_handler = _ERROR_HANDLER_FUNC(_py_error_handler)
    asound = cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(_c_error_handler)
except Exception:
    pass

try:
    import speech_recognition as sr
except ImportError:
    sr = None
from core.orchestrator import Orchestrator
from core.target_model import Target
from core.case_brief import CaseBrief, parse_brief_with_slm
from core.wake_word import WakeWordEngine
from narrative.soldierboy_voice import SoldierBoyVoice
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


class SoldierBoyAPI:
    def __init__(self):
        self._window = None
        self._target: Target = None
        self._memory = SessionMemory()
        self._voice = SoldierBoyVoice()
        self._lessons_store = LessonsStore()
        self._orch = None
        self._stalk_loop = None
        self._stalk_task = None
        self._last_entity = None  # Track for false-positive command
        self._wake_window_expires = 0.0
        self._recent_agent_responses = []
        self._tts_playback_until = 0.0

        # Async Background Initialization for Instant App Launch (<0.2s)
        self._wake_engine = None
        threading.Thread(target=self._async_init_wake_engine, daemon=True).start()

    def _async_init_wake_engine(self):
        try:
            print("[desktop] Spinning up openWakeWord engine in background...")
            self._wake_engine = WakeWordEngine(
                on_wake_detected=self._on_wake_word_detected,
                on_speech_ended=self._on_vad_speech_ended,
                silence_timeout_sec=2.5,
                max_window_sec=30.0
            )
            self._wake_engine.start()
            print("[desktop] Background wake engine ready.")
        except Exception as e:
            print(f"[desktop] Background wake engine init notice: {e}")

    def _on_wake_word_detected(self, phrase: str):
        print(f"[desktop] openWakeWord triggered ('{phrase}'). Opening STT command capture window.")
        now = time.time()
        self._wake_window_expires = now + 30.0
        self._emit("soldierboy_wake_word_detected", {"raw": phrase, "clean": ""})

    def _on_vad_speech_ended(self):
        print("[desktop] VAD detected post-speech silence. Closing STT command window early.")
        self._wake_window_expires = 0.0
        self._emit("soldierboy_vad_speech_end", {})

    def set_window(self, window):
        self._window = window
        self._orch = Orchestrator(
            on_status=self._on_status,
            on_find=self._on_find,
            on_done=lambda t: self._on_done(t, aborted=False),
            lessons_store=self._lessons_store,
        )

    def process_input(self, text: str):
        print(f"\n[desktop] Unified AI input received: {text}")
        self._memory.add("user", text)
        threading.Thread(target=self._run_process_input, args=(text,), daemon=True).start()

    def _on_skill_progress(self, finfo):
        if isinstance(finfo, dict) and "file" in finfo:
            msg_str = f"⚡ LIVE CODE AUDIT [{finfo['index']}/{finfo['total']}]: {finfo['file']} ({finfo['lines']} LOC)... [VERIFIED]"
            self._emit("open_soldierboy_panel", {
                "query": f"AUDITING {finfo['file']}",
                "text": msg_str,
                "typing_query": f"Audit [{finfo['index']}/{finfo['total']}]: {finfo['file']}",
                "action_type": "LIVE CODE AUDIT STREAM"
            })
            self._emit("scan_status", {"message": msg_str})

    def _run_process_input(self, text: str):
        try:
            # Fast-path check: system skills and search commands execute instantly without 2s intent classification latency
            if hasattr(self._voice, 'skills') and self._voice.skills:
                res = self._voice.skills.try_execute(text, on_progress=self._on_skill_progress)
                if len(res) == 5:
                    handled, msg, is_search, query, payload = res
                else:
                    handled, msg, is_search, query = res
                    payload = {}

                if handled:
                    display_query = query if query else text
                    print(f"[desktop] System skill/search fast-path triggered for: '{text}' (query: '{display_query}')")
                    self._emit("open_soldierboy_panel", {
                        "query": display_query,
                        "text": msg,
                        "typing_query": f"Executing action: {display_query}",
                        "action_type": "ACTION HUD ACTIVE",
                        "structured_payload": payload
                    })
                    self._emit("soldierboy_structured_json_feed", payload)

                    context_prompt = f"[REAL SYSTEM SKILL EXECUTED]\nUser Prompt: {text}\nExecution Output Data:\n{msg}\nStructured Payload: {json.dumps(payload, indent=2)}\n\nPersona Spoken Instructions: As Soldier Boy, give a short 2-sentence cocky, unfiltered partner summary of these REAL search/audit results. Speak only about the actual data provided above, do not invent fictional stories about Vought or Homelander."
                    self._run_ask(context_prompt)
                    return

            intent = self._voice.classify_intent(text, self._target)
            print(f"[desktop] AI Intent decision: {intent}")
            if intent["type"] == "investigate" and intent.get("target"):
                target_str = intent["target"]
                self._emit("scan_status", {"message": f"AI identified investigation task — Target: {target_str}"})
                brief = None
                if _CONTEXT_SIGNALS.search(text):
                    brief = parse_brief_with_slm(text)
                self._run_stalk(target_str, brief)
            else:
                self._run_ask(text)
        except Exception as e:
            print(f"[desktop] Error processing input: {e}")
            self._emit("error", {"message": f"Partner system error: {str(e)}"})

    def investigate(self, target: str):
        print(f"\n[desktop] Starting investigation: {target}")
        self._memory.add("user", f"investigate {target}")
        threading.Thread(target=self._run_stalk, args=(target, None), daemon=True).start()

    # Backward-compatible alias for older frontend builds calling api.stalk(...)
    stalk = investigate

    def smart_investigate(self, text: str):
        self.process_input(text)

    # Backward-compatible alias
    smart_stalk = smart_investigate

    def ask(self, question: str):
        self.process_input(question)

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
            self._emit("soldierboy_answer", {
                "text": f"Lesson learned about {platform}. I won't make that mistake again.",
                "rate_limited": False,
                "mode": "investigation" if self._target else "advisor",
            })
        else:
            self._emit("soldierboy_answer", {
                "text": "I can't store lessons right now — memory modules aren't installed.",
                "rate_limited": False,
                "mode": "advisor",
            })

    @staticmethod
    def _is_placeholder(val):
        """Check if a config value is a placeholder like YOUR_..._HERE."""
        if not val or not isinstance(val, str):
            return True
        return val.startswith("YOUR_") or val.endswith("_HERE")

    def get_config(self):
        """Load config.yaml and return as dict for the settings UI."""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    config = yaml.safe_load(f) or {}

                # Filter out placeholder values so the form shows empty instead
                def clean(key, default=""):
                    val = config.get(key, default)
                    return "" if self._is_placeholder(val) else val

                return {
                    "model": config.get("model", ""),
                    "ollama_url": config.get("ollama_url", "http://localhost:11434"),
                    "gemini_api_key": clean("gemini_api_key"),
                    "nvidia_api_key": clean("nvidia_api_key"),
                    "nvidia_model": config.get("nvidia_model", "nvidia/nemotron-3-super-120b-a12b"),
                    "fish_audio_api_key": clean("fish_audio_api_key"),
                    "fish_audio_voice_id": config.get("fish_audio_voice_id", "e81ae965a9a94ed69ff05eed7e7a57c7"),
                    "tools": config.get("tools", {}),
                }
        except Exception as e:
            print(f"[desktop] Error loading config: {e}")
        return {}

    def toggle_voice(self, enabled: bool):
        """Voice synthesis toggle."""
        return True

    def toggle_json_mode(self, enabled: bool = None) -> bool:
        """Toggle structured JSON payload mode."""
        if hasattr(self._voice, 'skills') and self._voice.skills:
            return self._voice.skills.hud_engine.toggle_json_mode(enabled)
        return True

    def get_structured_json_feed(self) -> dict:
        """Fetch latest active JSON payload from state file."""
        state_file = Path(__file__).parent.parent.resolve() / "data" / "structured_hud_active.json"
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"status": "IDLE", "findings": []}

    def clear_search_cache(self) -> str:
        """Clear search cache entries."""
        if hasattr(self._voice, 'skills') and self._voice.skills:
            return self._voice.skills.hud_engine.cache.clear()
        return "Cache cleared."

    def save_config(self, cfg: dict):
        """Save settings from the UI back to config.yaml."""
        try:
            existing = {}
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    existing = yaml.safe_load(f) or {}

            field_map = {
                "model": "model",
                "ollama_url": "ollama_url",
                "gemini_api_key": "gemini_api_key",
                "nvidia_api_key": "nvidia_api_key",
                "nvidia_model": "nvidia_model",
                "fish_audio_api_key": "fish_audio_api_key",
                "fish_audio_voice_id": "fish_audio_voice_id",
            }
            for ui_key, yaml_key in field_map.items():
                if ui_key in cfg:
                    existing[yaml_key] = cfg[ui_key]

            if "tools" in cfg and isinstance(cfg["tools"], dict):
                existing.setdefault("tools", {})
                existing["tools"].update(cfg["tools"])

            with open(CONFIG_PATH, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, sort_keys=False)

            self._voice = SoldierBoyVoice()

            engine = "SLM"
            if self._voice.nvidia_available:
                engine = f"NVIDIA NIM ({self._voice.nvidia_model})"
            elif self._voice.gemini_available:
                engine = "Gemini"

            print(f"[desktop] Config saved → active engine: {engine}")
            self._emit("config_saved", {"engine": engine})
            return True
        except Exception as e:
            print(f"[desktop] Error saving config: {e}")
            self._emit("error", {"message": f"Failed to save config: {e}"})
            return False

    def get_evidence_list(self) -> list:
        """Return list of captured evidence screenshot items for the active case."""
        if not self._target:
            return []
        evidence_items = []
        try:
            case_slug = self._target.primary.replace("@", "_").replace(".", "_")
            evidence_dir = Path.home() / ".soldierboy" / "cases" / case_slug / "evidence"
            if not evidence_dir.exists():
                evidence_dir = Path.home() / ".joe" / "cases" / case_slug / "evidence"
            if evidence_dir.exists():
                for p in evidence_dir.glob("*.png"):
                    evidence_items.append({
                        "filename": p.name,
                        "path": str(p),
                        "time": time.ctime(p.stat().st_mtime)
                    })
        except Exception as e:
            print(f"[desktop] Error listing evidence: {e}")
        return evidence_items

    def get_model_info(self):
        model = self._voice.slm_model
        using_gemini = self._voice.gemini_available and not self._voice.gemini_rate_limited
        nvidia_available = getattr(self._voice, 'nvidia_available', False)
        self._emit("model_info", {"model": model, "using_gemini": using_gemini, "nvidia_available": nvidia_available})

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
        match = re.match(r"^(investigate|stalk|pivot)\s+(\S+)", text, re.IGNORECASE)
        if match and match.group(2).lower() not in ("again", "them", "him", "her", "it", "to", "the", "me"):
            target_str = match.group(2)
        else:
            target_str = self._voice.extract_target(text, self._target)

        if not target_str or target_str.lower() == "none":
            self._emit("error", {"message": "Who do you want me to look into? I need a clear target."})
            return

        self._emit("scan_status", {"message": f"Target locked: {target_str}"})

        # Extract brief from context beyond the target
        # If the user typed "investigate johndoe — they worked at Acme Corp"
        # strip the command and target, use the rest as brief
        brief = None
        remainder = text
        # Remove command prefix
        for prefix in ["investigate ", "stalk ", "pivot "]:
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

    def _synthesize_and_emit_sentence(self, sentence: str):
        if not self._voice:
            return
        try:
            if sentence and len(sentence.strip()) > 2:
                self._recent_agent_responses.append(sentence.strip())
                if len(self._recent_agent_responses) > 20:
                    self._recent_agent_responses.pop(0)
                self._tts_playback_until = time.time() + max(3.5, len(sentence) * 0.08)

            audio_b64 = self._voice.synthesize_speech_b64(sentence)
            if audio_b64:
                self._emit("soldierboy_audio_chunk", {"audio": audio_b64, "text": sentence})
        except Exception as e:
            print(f"[desktop] Sentence TTS streaming error: {e}")

    def _run_ask(self, question: str):
        self._emit("soldierboy_stream_start", {})
        sentence_buffer = ""
        tts_queue = queue.Queue()
        sent_count = 0

        def tts_worker():
            while True:
                item = tts_queue.get()
                if item is None:
                    tts_queue.task_done()
                    break
                try:
                    sentence = item
                    if sentence and len(sentence.strip()) > 2:
                        self._recent_agent_responses.append(sentence.strip())
                        if len(self._recent_agent_responses) > 20:
                            self._recent_agent_responses.pop(0)
                        self._tts_playback_until = time.time() + max(3.5, len(sentence) * 0.08)

                    audio_b64 = self._voice.synthesize_speech_b64(sentence)
                    if audio_b64:
                        self._emit("soldierboy_audio_chunk", {"audio": audio_b64, "text": sentence})
                except Exception as e:
                    print(f"[desktop] Sentence TTS streaming error: {e}")
                finally:
                    tts_queue.task_done()

        worker_thread = None
        if self._voice:
            worker_thread = threading.Thread(target=tts_worker, daemon=True)
            worker_thread.start()

        def on_token(chunk: str):
            nonlocal sentence_buffer, sent_count
            self._emit("soldierboy_stream_chunk", {"chunk": chunk})

            if self._voice:
                sentence_buffer += chunk
                # Python 3.14 safe sentence boundary matching
                m = re.search(r'([.!?\n]+)', sentence_buffer)
                if m:
                    sentence = sentence_buffer[:m.end()].strip()
                    sentence_buffer = sentence_buffer[m.end():]
                    if len(sentence) > 3:
                        sent_count += 1
                        clean_sentence = re.sub(r'(\w+)_(\w+)', r'\1 \2', sentence).replace('_', ' ')
                        tts_queue.put(clean_sentence)

        try:
            result = self._voice.chat(question, self._target, on_token=on_token)
        except Exception as e:
            print(f"[desktop] Voice chat execution error: {e}")
            result = {
                "text": f"Sorry, partner. Hit a slight snag processing that: {str(e)}",
                "error": True,
                "mode": "advisor"
            }

        if result.get("rate_limited"):
            self._emit("rate_limited", {})

        # Flush any remaining sentence buffer
        if sentence_buffer.strip() and self._voice:
            frag = sentence_buffer.strip()
            if len(frag) > 2:
                sent_count += 1
                tts_queue.put(frag)

        # System skill / non-streamed response TTS & text streaming fallback: if no streaming chunks were generated,
        # simulate word-by-word text streaming on screen AND enqueue clean spoken sentences for local voice engine!
        if sent_count == 0 and result.get("text"):
            raw_text = result["text"]
            # 1. Simulate streaming text on screen word-by-word
            words = raw_text.split(' ')
            for i, w in enumerate(words):
                token = w + (" " if i < len(words) - 1 else "")
                self._emit("soldierboy_stream_chunk", {"chunk": token})
                time.sleep(0.003)  # 3ms ultra-fast word typing effect

            # 2. Extract clean printable sentences for speech synthesis
            if self._voice:
                clean_lines = []
                for line in raw_text.splitlines():
                    line_s = line.strip()
                    if not line_s:
                        continue
                    line_s = re.sub(r'^(?:\d+\.|\bullet|[\*\-\+])\s*', '', line_s).strip()
                    if line_s:
                        clean_lines.append(line_s)
                
                full_clean = ". ".join(clean_lines)
                sentences = re.split(r'(?<=[.!?])\s+', full_clean)
                for s in sentences:
                    s_clean = s.strip()
                    if len(s_clean) > 3:
                        tts_queue.put(s_clean)

        if worker_thread:
            tts_queue.put(None)

        # Post-hoc grounding check audit on full assembled LLM response text
        if self._target and result.get("text"):
            try:
                from narrative.grounding_check import verify_grounding
                _, warnings = verify_grounding(result["text"], self._target)
                if warnings:
                    print(f"[desktop] Grounding audit warning for active case {self._target.primary}: {warnings}")
                    self._emit("soldierboy_grounding_warning", {"warnings": warnings, "target": self._target.primary})
            except Exception as e:
                print(f"[desktop] Post-hoc grounding check audit notice: {e}")

        self._emit("soldierboy_answer", {
            "text": result.get("text", "Done."),
            "audio": None,
            "rate_limited": result.get("rate_limited", False),
            "mode": result.get("mode", "advisor"),
            "error": result.get("error", False),
            "open_dialog": result.get("open_dialog", False),
            "show_panel": result.get("show_panel", False),
            "search_query": result.get("search_query", "")
        })
        if result.get("open_dialog"):
            self._emit("open_investigate_dialog", {})
        if result.get("show_panel"):
            self._emit("open_soldierboy_panel", {
                "query": result.get("search_query", ""),
                "text": result["text"],
                "structured_payload": result.get("panel_payload", {})
            })
        if "Generating HTML investigation report" in result.get("text", ""):
            self.export_report()
        self._wake_window_expires = time.time() + 30.0

    def export_report(self) -> str:
        """Export current investigation target findings to a standalone HTML report."""
        if not self._target:
            msg = "No active investigation case loaded to export."
            self._emit("soldierboy_answer", {"text": msg, "mode": "advisor"})
            return msg
        try:
            from exporters.html_report import generate
            report_path = generate(self._target)
            msg = f"HTML investigation report generated successfully at: {report_path}"
            print(f"[desktop] {msg}")
            self._emit("soldierboy_answer", {"text": f"Report exported for {self._target.primary}. Saved to: {report_path}", "mode": "investigation"})
            return str(report_path)
        except Exception as e:
            err_msg = f"Failed to export report: {e}"
            print(f"[desktop] {err_msg}")
            self._emit("soldierboy_answer", {"text": err_msg, "mode": "advisor"})
            return err_msg

    def pick_image(self):
        """Open native file dialog to select an image for analysis."""
        if not self._window:
            return
        try:
            file_types = ('Image Files (*.png;*.jpg;*.jpeg;*.gif;*.webp)', 'All files (*.*)')
            result = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
            if result and len(result) > 0:
                src_path = Path(result[0])
                if src_path.exists():
                    attachments_dir = ROOT.parent / "cases" / "attachments"
                    attachments_dir.mkdir(parents=True, exist_ok=True)
                    dest_path = attachments_dir / src_path.name
                    import shutil
                    shutil.copy(src_path, dest_path)
                    rel_path = f"cases/attachments/{src_path.name}"
                    self._emit("image_selected", {"path": rel_path, "filename": src_path.name})
        except Exception as e:
            print(f"[desktop] pick_image error: {e}")

    def save_dropped_image(self, data_url: str, filename: str):
        """Save base64 data URL image dropped or picked via web file input."""
        try:
            import base64
            if "," in data_url:
                data_url = data_url.split(",", 1)[1]
            raw_bytes = base64.b64decode(data_url)
            attachments_dir = ROOT.parent / "cases" / "attachments"
            attachments_dir.mkdir(parents=True, exist_ok=True)
            dest_path = attachments_dir / filename
            dest_path.write_bytes(raw_bytes)
            rel_path = f"cases/attachments/{filename}"
            self._emit("image_selected", {"path": rel_path, "filename": filename})
        except Exception as e:
            print(f"[desktop] save_dropped_image error: {e}")

    def submit_image(self, image_path: str, prompt: str):
        """Analyze an attached image with prompt via SoldierBoyVoice multimodal AI."""
        print(f"\n[desktop] Submitting image prompt: {prompt} (image: {image_path})")
        threading.Thread(target=self._run_submit_image, args=(image_path, prompt), daemon=True).start()

    def _run_submit_image(self, image_path: str, prompt: str):
        self._emit("soldierboy_stream_start", {})
        def on_token(chunk: str):
            self._emit("soldierboy_stream_chunk", {"chunk": chunk})

        full_prompt = prompt if prompt else "Analyze this image in detail and tell me what you observe from an OSINT investigator perspective."
        result = self._voice.chat(full_prompt, self._target, on_token=on_token, image_path=image_path)
        if result.get("rate_limited"):
            self._emit("rate_limited", {})

        self._emit("soldierboy_answer", {
            "text": result["text"],
            "audio": None,
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
            self._emit("soldierboy_stream_start", {})
            def on_token(chunk: str):
                self._emit("soldierboy_stream_chunk", {"chunk": chunk})

            result = self._voice.closing_monologue(target, on_token=on_token)
            text = result["text"]
            used_gemini = result.get("used_gemini", False)
            error = result.get("error", False)
            if result.get("rate_limited"):
                self._emit("rate_limited", {})

        self._memory.add("soldierboy", text)
        self._emit("investigation_done", {
            "target": target.to_dict(),
            "monologue": text,
            "audio": None,
            "used_gemini": used_gemini,
            "error": error
        })

    def transcribe_audio(self, audio_b64: str) -> dict:
        """
        Receives base64 audio payload from frontend, converts to WAV via ffmpeg,
        and transcribes text using speech_recognition.
        """
        import base64
        import tempfile
        import subprocess
        import os
        try:
            import speech_recognition as sr
        except ImportError:
            return {"success": False, "error": "speech_recognition package not installed"}

        if not audio_b64:
            return {"success": False, "error": "Empty audio payload"}

        in_path = None
        out_path = None
        try:
            if "," in audio_b64:
                audio_b64 = audio_b64.split(",", 1)[1]

            raw_bytes = base64.b64decode(audio_b64)
            
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
                tmp_in.write(raw_bytes)
                in_path = tmp_in.name

            out_path = in_path + ".wav"

            cmd = ["ffmpeg", "-y", "-i", in_path, "-ac", "1", "-ar", "16000", out_path]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            target_file = out_path if (os.path.exists(out_path) and os.path.getsize(out_path) > 0) else in_path

            recognizer = sr.Recognizer()
            with sr.AudioFile(target_file) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data)

            return {"success": True, "text": text}
        except sr.UnknownValueError:
            return {"success": False, "error": "Speech was unintelligible"}
        except sr.RequestError as e:
            return {"success": False, "error": f"Speech API error: {e}"}
        except Exception as e:
            print(f"[desktop] Audio transcription error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            for p in (in_path, out_path):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    def start_native_mic(self):
        """Start native Linux microphone recording via verified ffmpeg/arecord/rec background process."""
        if hasattr(self, '_mic_proc') and self._mic_proc and self._mic_proc.poll() is None:
            return {"success": True, "recording": True}

        wav_path = "/tmp/joe_mic_rec.wav"
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

        candidates = [
            ["arecord", "-D", "default", "-f", "S16_LE", "-r", "16000", "-c", "1", wav_path],
            ["arecord", "-D", "plughw:1,0", "-f", "S16_LE", "-r", "16000", "-c", "1", wav_path],
            ["ffmpeg", "-y", "-f", "alsa", "-i", "default", "-ar", "16000", "-ac", "1", wav_path],
            ["ffmpeg", "-y", "-f", "pulse", "-i", "default", "-ar", "16000", "-ac", "1", wav_path],
            ["rec", "-r", "16000", "-c", "1", wav_path],
        ]

        last_err = ""
        for cmd in candidates:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(0.15)
                if proc.poll() is None:
                    self._mic_proc = proc
                    self._mic_start_time = time.time()
                    print(f"[desktop] Native mic recording active via {cmd[0]}...")
                    return {"success": True, "recording": True}
                else:
                    _, err_bytes = proc.communicate()
                    last_err = err_bytes.decode('utf-8', errors='ignore')
                    print(f"[desktop] Mic cmd {cmd[0]} exited prematurely: {last_err[:150]}")
            except Exception as e:
                last_err = str(e)
                print(f"[desktop] Failed launching mic candidate {cmd[0]}: {e}")

        return {"success": False, "error": f"Failed starting microphone recording: {last_err[:150]}"}

    def stop_native_mic(self):
        """Stop native Linux microphone recording and transcribe using Google Speech Recognition."""
        if not hasattr(self, '_mic_proc') or not self._mic_proc:
            return {"success": False, "error": "No microphone recording in progress"}

        # Ensure minimum 1.2s audio capture to prevent 0-byte recording on fast clicks
        if hasattr(self, '_mic_start_time'):
            elapsed = time.time() - self._mic_start_time
            if elapsed < 1.2:
                time.sleep(1.2 - elapsed)

        try:
            self._mic_proc.terminate()
            try:
                self._mic_proc.wait(timeout=1.5)
            except Exception:
                self._mic_proc.kill()
        except Exception as e:
            print(f"[desktop] Terminate mic process error: {e}")
        finally:
            self._mic_proc = None

        wav_path = "/tmp/joe_mic_rec.wav"
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            return {"success": False, "error": "No audio captured from microphone"}

        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data)

            return {"success": True, "text": text}
        except sr.UnknownValueError:
            return {"success": False, "error": "Speech was unintelligible"}
        except sr.RequestError as e:
            return {"success": False, "error": f"Speech API error: {e}"}
        except Exception as e:
            print(f"[desktop] Native mic transcribe error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    def start_background_voice_listener(self):
        """Start a background daemon thread that continuously listens for speech."""
        if hasattr(self, '_bg_voice_thread') and self._bg_voice_thread and self._bg_voice_thread.is_alive():
            return {"success": True, "status": "running"}

        self._bg_voice_active = True
        self._bg_voice_thread = threading.Thread(target=self._bg_voice_loop, daemon=True)
        self._bg_voice_thread.start()
        print("[desktop] Automatic background voice listener activated...")
        return {"success": True, "status": "started"}

    def _bg_voice_loop(self):
        """
        Native high-responsiveness continuous VAD listener.
        Reads 100ms PCM audio chunks via arecord/ffmpeg with stderr redirected to DEVNULL
        (eliminating JACK/ALSA terminal noise).

        Triggers INSTANT HUD movement (listening state) within 100ms of speech start,
        detects silence after 0.4s, and transcribes speech using Google Speech Recognition.
        """
        if not sr:
            print("[desktop] Voice listener disabled: speech_recognition package not installed.")
            return

        candidates = [
            ["arecord", "-D", "default", "-f", "S16_LE", "-r", "16000", "-c", "1", "-q", "-"],
            ["arecord", "-D", "plughw:1,0", "-f", "S16_LE", "-r", "16000", "-c", "1", "-q", "-"],
            ["ffmpeg", "-loglevel", "quiet", "-f", "alsa", "-i", "default", "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
            ["ffmpeg", "-loglevel", "quiet", "-f", "pulse", "-i", "default", "-ar", "16000", "-ac", "1", "-f", "s16le", "-"]
        ]

        proc = None
        for cmd in candidates:
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                # Test read 100ms
                test_bytes = p.stdout.read(3200)
                if test_bytes and len(test_bytes) > 0:
                    proc = p
                    break
                else:
                    p.terminate()
            except Exception:
                continue

        if not proc:
            print("[desktop] Background voice listener: no usable native mic capture tool found.")
            return

        wake_window_expires = 0.0
        ambient_energy = 150.0
        is_speaking = False
        speech_start_count = 0
        silence_chunks = 0
        pcm_buffer = []

        chunk_size = 3200  # 100ms @ 16kHz 16-bit mono

        try:
            while getattr(self, '_bg_voice_active', False) and proc.poll() is None:
                # 0. If TTS playback is actively outputting speech through speakers, pause mic recording to prevent echo feedback loop
                if time.time() < getattr(self, '_tts_playback_until', 0.0):
                    pcm_buffer.clear()
                    is_speaking = False
                    silence_chunks = 0
                    speech_start_count = 0
                    time.sleep(0.08)
                    continue

                raw_chunk = proc.stdout.read(chunk_size)
                if not raw_chunk or len(raw_chunk) < chunk_size:
                    time.sleep(0.05)
                    continue

                # Calculate RMS energy of 100ms chunk
                shorts = struct.unpack(f"<{len(raw_chunk)//2}h", raw_chunk)
                if not shorts:
                    continue
                sum_sq = sum(s * s for s in shorts)
                energy = (sum_sq / len(shorts)) ** 0.5

                # Threshold to filter breathing / room rustles (min 1000.0)
                threshold = max(1000.0, ambient_energy * 3.0)

                if energy > threshold:
                    speech_start_count += 1
                    silence_chunks = 0
                    pcm_buffer.append(raw_chunk)

                    # Require 2 consecutive chunks (>200ms) of real speech energy to start recording
                    if speech_start_count >= 2 and not is_speaking:
                        is_speaking = True
                        print(f"[voice listener] Voice detected (Energy: {energy:.1f} > Threshold: {threshold:.1f}) -> HUD set to LISTENING...")
                        self._emit("soldierboy_speech_started", {})
                else:
                    speech_start_count = 0
                    # Ambient background noise tracking
                    ambient_energy = 0.95 * ambient_energy + 0.05 * energy
                    if is_speaking:
                        pcm_buffer.append(raw_chunk)
                        silence_chunks += 1

                        # 25 consecutive silence chunks = 2.5s silence hangover -> allows user pauses without cutting off mid-sentence
                        if silence_chunks >= 25:
                            is_speaking = False
                            silence_chunks = 0
                            captured_pcm = b"".join(pcm_buffer)
                            pcm_buffer = []

                            duration_sec = len(captured_pcm) / 32000.0
                            print(f"[voice listener] Speech completed (2.5s silence). Captured {duration_sec:.1f}s of audio. Transcribing...")

                            if len(captured_pcm) >= 32000:
                                threading.Thread(
                                    target=self._process_captured_speech,
                                    args=(captured_pcm,),
                                    daemon=True
                                ).start()
                            else:
                                self._emit("soldierboy_speech_ended", {})
        except Exception as e:
            import traceback
            print(f"[desktop] Background voice loop error: {e}")
            traceback.print_exc()
        finally:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

    def _process_captured_speech(self, pcm_bytes: bytes):
        """Transcribe captured speech and trigger HUD / SoldierBoyVoice response."""
        # 1. Ignore audio captured while TTS was playing back
        if time.time() < getattr(self, '_tts_playback_until', 0.0):
            print("[voice listener] Captured audio ignored: TTS audio was active during recording.")
            self._emit("soldierboy_speech_ended", {})
            return

        wav_path = f"/tmp/soldierboy_speech_{int(time.time()*1000)}.wav"
        try:
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_bytes)

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data).strip()

            if text:
                print(f"[voice listener] Recognized text: '{text}'")

                # 2. Filter out self-echo (mic picking up Soldier Boy's own voice)
                rec_clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
                is_self_echo = False
                for past_resp in getattr(self, '_recent_agent_responses', []):
                    past_clean = re.sub(r'[^\w\s]', '', past_resp.lower()).strip()
                    if not past_clean or not rec_clean:
                        continue
                    if rec_clean in past_clean or past_clean in rec_clean:
                        is_self_echo = True
                        break
                    rec_words = set(rec_clean.split())
                    past_words = set(past_clean.split())
                    if rec_words and past_words:
                        overlap = len(rec_words & past_words) / len(rec_words)
                        if overlap > 0.6 and len(rec_words) >= 3:
                            is_self_echo = True
                            break

                if is_self_echo:
                    print(f"[voice listener] Self-echo suppressed (recognized text matches Soldier Boy response): '{text}'")
                    self._emit("soldierboy_speech_ended", {})
                    return

                # Check for explicit Stop commands first
                stop_pattern = r'\b(?:stop|shut\s*up|be\s*quiet|quiet|hush|silence|cancel)\b'
                if re.search(stop_pattern, text, re.IGNORECASE):
                    print(f"[voice listener] Stop command detected: '{text}'")
                    self._emit("soldierboy_stop_command", {"text": text})
                    self._wake_window_expires = 0.0
                    return

                # Comprehensive Soldier Boy wake word pattern (handling all Google STT acoustic mishears: your, you, u, ya, Suraj, search, shoes, soulja, etc.)
                pattern = r'^(?:(?:hey|hi|hai|yo|yoo|you|your|ur|u|ya|bro|dude|hello|ok|okay|play)\s+)?(?:soldier\s*boy|soldier|soldi|soldja|solger|solja|soja|solda|suraj\s*boy|suraj|search\s*boy|shoes\s*boy|soulja\s*boy|soulja|shoulda\s*boy|sol)\b\s*,?\s*'
                match = re.search(pattern, text, re.IGNORECASE)
                anywhere_match = re.search(r'\b(?:soldier\s*boy|soldier|soldja|solger|solja|suraj\s*boy|suraj|soulja\s*boy|soulja)\b', text, re.IGNORECASE)
                now = time.time()

                # Direct identity / interaction questions bypass wake word check
                implicit_match = re.search(r'\b(?:who\s+are\s+you|who\s+are\s+u|who\s+u\s+are|what\s+can\s+you\s+do|who\s+the\s+fuck\s+are\s+you)\b', text, re.IGNORECASE)

                if match:
                    clean = text[match.end():].strip()
                    print(f"[voice listener] Wake word match! Raw: '{text}', Clean command: '{clean}'")
                    self._emit("soldierboy_wake_word_detected", {"raw": text, "clean": clean if clean else text})
                    if clean:
                        print(f"[voice listener] Sending voice command to Soldier Boy: '{clean}'")
                        self._emit("soldierboy_voice_detected", {"text": clean, "raw": text})
                        self._wake_window_expires = now + 30.0
                    else:
                        print(f"[voice listener] Wake word only spoken ('{text}'). Opening 30s follow-up window...")
                        self._wake_window_expires = now + 30.0
                elif anywhere_match:
                    print(f"[voice listener] Anywhere wake phrase match ('{text}')! Triggering Soldier Boy command...")
                    self._emit("soldierboy_wake_word_detected", {"raw": text, "clean": text})
                    self._emit("soldierboy_voice_detected", {"text": text, "raw": text})
                    self._wake_window_expires = now + 30.0
                elif implicit_match:
                    print(f"[voice listener] Direct query match ('{text}')! Triggering Soldier Boy command...")
                    self._emit("soldierboy_wake_word_detected", {"raw": text, "clean": text})
                    self._emit("soldierboy_voice_detected", {"text": text, "raw": text})
                    self._wake_window_expires = now + 30.0
                elif now < getattr(self, '_wake_window_expires', 0.0):
                    print(f"[voice listener] Active wake window! Sending follow-up command to Soldier Boy: '{text}'")
                    self._emit("soldierboy_voice_detected", {"text": text, "raw": text})
                    self._wake_window_expires = now + 30.0
                else:
                    print(f"[voice listener] No wake word detected in ambient audio: '{text}'")
                    self._emit("soldierboy_speech_ended", {})
            else:
                print("[voice listener] Audio transcribed to empty text.")
                self._emit("soldierboy_speech_ended", {})

        except sr.UnknownValueError:
            print("[voice listener] Audio was unintelligible.")
            self._emit("soldierboy_speech_ended", {})
        except sr.RequestError as req_err:
            print(f"[voice listener] Google Speech Recognition API error: {req_err}")
            self._emit("soldierboy_speech_ended", {})
        except Exception as e:
            import traceback
            print(f"[desktop] Processing error: {e}")
            traceback.print_exc()
            self._emit("soldierboy_speech_ended", {})
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    def _emit(self, event: str, data: dict):
        if self._window:
            try:
                js_code = f"(window.soldierboy || window.joe) && (window.soldierboy || window.joe).receive && (window.soldierboy || window.joe).receive('{event}', {json.dumps(data)})"
                self._window.evaluate_js(js_code)
            except Exception as e:
                print(f"[desktop] JS evaluate error for {event}: {e}")


class SoldierBoyDesktop:
    def launch(self):
        import shutil

        # Copy icons and artwork assets to frontend execution directory
        src_icon = ROOT.parent / "assets" / "soldierboy-icon.png"
        dst_icon = ROOT / "soldierboy-icon.png"
        if src_icon.exists():
            shutil.copy(src_icon, dst_icon)

        src_back = ROOT.parent / "assets" / "soldierboygui.png"
        dst_back = ROOT / "soldierboygui.png"
        if src_back.exists():
            shutil.copy(src_back, dst_back)

        src_geo = ROOT.parent / "assets" / "world_outline.jpg"
        dst_geo = ROOT / "world_outline.jpg"
        if src_geo.exists() and not dst_geo.exists():
            shutil.copy(src_geo, dst_geo)

        # Wire GTK desktop app window icon for Linux taskbar/dock/alt-tab
        if dst_icon.exists():
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk, GdkPixbuf
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(dst_icon))
                Gtk.Window.set_default_icon(pixbuf)
                print(f"[desktop] Bound GTK window & taskbar icon: {dst_icon}")
            except Exception as e:
                print(f"[desktop] GTK icon notice: {e}")

        api = SoldierBoyAPI()
        window_kwargs = {
            "title": "Soldier Boy",
            "url": str(HTML_PATH),
            "js_api": api,
            "width": 1200,
            "height": 780,
            "min_size": (900, 600),
            "background_color": "#120e0b",
        }

        window = webview.create_window(**window_kwargs)

        api.set_window(window)
        api.start_background_voice_listener()
        webview.start(debug=False)