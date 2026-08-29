# frontend/desktop.py
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

import webview
import asyncio
import threading
import json
import re
import subprocess
import time
import os
from pathlib import Path

try:
    import speech_recognition as sr
except ImportError:
    sr = None
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

    def process_input(self, text: str):
        print(f"\n[desktop] Unified AI input received: {text}")
        self._memory.add("user", text)
        threading.Thread(target=self._run_process_input, args=(text,), daemon=True).start()

    def _run_process_input(self, text: str):
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

    def stalk(self, target: str):
        print(f"\n[desktop] Starting investigation: {target}")
        self._memory.add("user", f"stalk {target}")
        threading.Thread(target=self._run_stalk, args=(target, None), daemon=True).start()

    def smart_stalk(self, text: str):
        self.process_input(text)

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
                    "nvidia_model": config.get("nvidia_model", "meta/llama-3.2-11b-vision-instruct"),
                    "tools": config.get("tools", {}),
                }
        except Exception as e:
            print(f"[desktop] Error loading config: {e}")
        return {}

    def toggle_voice(self, enabled: bool):
        """Voice synthesis is disabled — Joe is text-to-text only."""
        return False

    def save_config(self, cfg: dict):
        """Save settings from the UI back to config.yaml."""
        try:
            # Load existing config to preserve fields the UI doesn't expose
            existing = {}
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    existing = yaml.safe_load(f) or {}

            # Write every field the UI sends — use 'in' not .get() so empty
            # strings are written (allowing users to clear fields)
            field_map = {
                "model": "model",
                "ollama_url": "ollama_url",
                "gemini_api_key": "gemini_api_key",
                "nvidia_api_key": "nvidia_api_key",
                "nvidia_model": "nvidia_model",
            }
            for ui_key, yaml_key in field_map.items():
                if ui_key in cfg:
                    existing[yaml_key] = cfg[ui_key]

            if "tools" in cfg and isinstance(cfg["tools"], dict):
                existing.setdefault("tools", {})
                existing["tools"].update(cfg["tools"])

            with open(CONFIG_PATH, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, sort_keys=False)

            # Hot-reload the voice engine with new keys so changes take
            # effect immediately without restarting
            self._voice = JoeVoice()

            engine = "SLM"
            if self._voice.nvidia_available:
                engine = "NVIDIA NIM"
            elif self._voice.gemini_available:
                engine = "Gemini"

            print(f"[desktop] Config saved → active engine: {engine}")
            self._emit("config_saved", {"engine": engine})
            return True
        except Exception as e:
            print(f"[desktop] Error saving config: {e}")
            self._emit("error", {"message": f"Failed to save config: {e}"})
            return False

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
        self._emit("joe_stream_start", {})
        def on_token(chunk: str):
            self._emit("joe_stream_chunk", {"chunk": chunk})

        result = self._voice.chat(question, self._target, on_token=on_token)
        if result.get("rate_limited"):
            self._emit("rate_limited", {})

        self._emit("joe_answer", {
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
            self._emit("joe_stream_start", {})
            def on_token(chunk: str):
                self._emit("joe_stream_chunk", {"chunk": chunk})

            result = self._voice.closing_monologue(target, on_token=on_token)
            text = result["text"]
            used_gemini = result.get("used_gemini", False)
            error = result.get("error", False)
            if result.get("rate_limited"):
                self._emit("rate_limited", {})

        self._memory.add("joe", text)
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
        if not sr:
            print("[desktop] Voice listener disabled: speech_recognition package not installed in environment.")
            return

        wav_path = "/tmp/joe_auto_voice.wav"
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        rec_candidates = [
            ["arecord", "-D", "plughw:1,0", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", "2", wav_path],
            ["arecord", "-D", "default", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", "2", wav_path],
            ["ffmpeg", "-y", "-f", "alsa", "-i", "default", "-ar", "16000", "-ac", "1", "-t", "2", wav_path],
            ["ffmpeg", "-y", "-f", "pulse", "-i", "default", "-ar", "16000", "-ac", "1", "-t", "2", wav_path]
        ]

        # Probe candidate commands to find the single working command for this system
        working_cmd = None
        for cmd in rec_candidates:
            if os.path.exists(wav_path):
                try: os.remove(wav_path)
                except Exception: pass
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.wait(timeout=3)
                if os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
                    working_cmd = cmd
                    print(f"[desktop] Audio capture device initialized: {' '.join(cmd[:4])}")
                    break
            except Exception:
                pass

        if not working_cmd:
            working_cmd = rec_candidates[0]

        while getattr(self, '_bg_voice_active', False):
            try:
                if os.path.exists(wav_path):
                    try: os.remove(wav_path)
                    except Exception: pass

                proc = subprocess.Popen(working_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()

                if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000:
                    time.sleep(0.1)
                    continue

                with sr.AudioFile(wav_path) as source:
                    audio_data = recognizer.record(source)
                    text = recognizer.recognize_google(audio_data).strip()

                if text:
                    print(f"[voice listener] Recognized: '{text}'")
                    pattern = r'^(?:(?:hey|hi|hai|yo|hello)\s+)?(?:joe|jo|zho|joey)\b\s*,?\s*|\b(?:joe|jo|zho|joey)\b\s*,?\s*'
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        clean = text[match.end():].strip()
                        # Wake word detected — immediately activate HUD listening mode
                        self._emit("joe_wake_word_detected", {"raw": text, "clean": clean})
                        if clean:
                            # Command followed the wake word (e.g. "Joe search for target")
                            self._emit("joe_voice_detected", {"text": clean, "raw": text})
                            time.sleep(1.0)
                    else:
                        # Follow-up speech while already listening
                        self._emit("joe_voice_detected", {"text": text, "raw": text})
                        time.sleep(0.8)
            except sr.UnknownValueError:
                pass
            except Exception as e:
                time.sleep(0.2)

    def _emit(self, event: str, data: dict):
        if self._window:
            try:
                js_code = f"window.joe && window.joe.receive && window.joe.receive('{event}', {json.dumps(data)})"
                self._window.evaluate_js(js_code)
            except Exception as e:
                print(f"[desktop] JS evaluate error for {event}: {e}")


class JoeDesktop:
    def launch(self):
        import shutil
        src_icon = ROOT.parent / "assets" / "joe-icon.png"
        dst_icon = ROOT / "joe-icon.png"
        if src_icon.exists() and not dst_icon.exists():
            shutil.copy(src_icon, dst_icon)

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
            background_color="#120e0b",
        )

        api.set_window(window)
        api.start_background_voice_listener()
        webview.start(debug=False)