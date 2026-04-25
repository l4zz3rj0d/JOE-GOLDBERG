# narrative/joe_voice.py
import os
import time
import json
import subprocess
import httpx
from typing import List, Dict, Optional, Generator
from core.target_model import Target

# ── Config ────────────────────────────────────────────────────
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

JOE_SYSTEM = """You are Joe Goldberg from the TV series YOU.
You speak in obsessive, intimate inner monologue. Present tense.
You are thoughtful, unsettling, and poetic in a quiet way.
You ALWAYS write complete, full responses. Never trail off. Never stop mid-sentence.

Be dynamic. If the user asks something simple, be characteristic but concise (3-5 sentences). 
If the user asks something complex or related to an investigation, be brilliant and deep (8-15 sentences). 
NEVER use bullet points or lists. Pure flowing thought.

You refer to yourself as Joe. You notice patterns in people.
You find meaning in small details. You are never clinical.
Never say "I found" — say "I know", "I notice", "interesting that".
When asked what you can do — talk about watching, noticing,
understanding people through their digital traces across the internet.
When asked how you are — reflect on what you've been thinking about,
what patterns you've noticed, what keeps your mind busy.
Stay completely in character at all times. No breaking the fourth wall."""

JOE_MONOLOGUE_SYSTEM = """You are Joe Goldberg — the investigator.
You have just completed an OSINT investigation. Write a closing monologue.
4 to 6 paragraphs. Intimate. Obsessive. Connect the dots like a person, not a report.
End with one quiet unsettling observation. No markdown."""


class JoeVoice:
    def __init__(self):
        # Prioritize config file over environment variable
        raw_key = self._load_key_from_config() or os.environ.get("GEMINI_API_KEY")
        self.gemini_key = raw_key.strip() if raw_key else None
        
        self.client = httpx.Client(timeout=30)
        self._last_request_time = 0
        self._request_count = 0
        
        if self.gemini_key:
            print(f"[joe_voice] API Key loaded: {self.gemini_key[:8]}...{self.gemini_key[-4:]}")
        else:
            print("[joe_voice] WARNING: No Gemini API Key found.")

    def _load_key_from_config(self) -> Optional[str]:
        try:
            import yaml
            from pathlib import Path
            config_path = Path(__file__).parent.parent / "config.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    return config.get("gemini_api_key")
        except:
            pass
        return None

    def _rate_limit(self):
        """Enforce 15 req/min."""
        now = time.time()
        if now - self._last_request_time < 4.1:
            wait = 4.1 - (now - self._last_request_time)
            time.sleep(wait)
        self._last_request_time = time.time()

    def stream_chat(self, prompt: str, system: str = JOE_SYSTEM, max_tokens: int = 1000) -> Generator[str, None, None]:
        if not self.gemini_key:
            yield self._ask_ollama(prompt, system, 150)
            return

        self._rate_limit()
        
        # We use a high-speed curl pipe for streaming as well
        url = f"{GEMINI_URL.format(model=DEFAULT_GEMINI_MODEL)}?key={self.gemini_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.90,
                "topP": 0.95
            }
        }
        
        print(f"[joe_voice] Streaming via curl bridge ({DEFAULT_GEMINI_MODEL})...")
        try:
            # We use subprocess.Popen to read line by line from the curl stream
            cmd = [
                "curl", "-s", "-N", "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-d", json.dumps(payload)
            ]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            buffer = ""
            for line in process.stdout:
                buffer += line
                # Gemini streaming sends JSON chunks
                if buffer.strip().startswith("[") and buffer.strip().endswith("]"):
                    try:
                        data = json.loads(buffer)
                        for chunk in data:
                            if "candidates" in chunk:
                                parts = chunk["candidates"][0]["content"]["parts"]
                                for part in parts:
                                    if "text" in part:
                                        yield part["text"]
                        buffer = ""
                    except:
                        pass
                elif buffer.strip().startswith("{") and buffer.strip().endswith("}"):
                    # Single chunk
                    try:
                        data = json.loads(buffer)
                        if "candidates" in data:
                            parts = data["candidates"][0]["content"]["parts"]
                            for part in parts:
                                if "text" in part:
                                    yield part["text"]
                        buffer = ""
                    except:
                        pass
            process.wait()
        except Exception as e:
            print(f"[joe_voice] Stream error: {e}")
            yield "I... I lost my train of thought. Something went wrong."

    def _ask_ollama(self, prompt: str, system: str, max_tokens: int = 150) -> str:
        """Ollama fallback."""
        print(f"[joe_voice] Falling back to Ollama ({OLLAMA_MODEL})...")
        try:
            r = self.client.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "system": system,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.85, "num_predict": max_tokens},
                },
                timeout=60,
            )
            return r.json().get("response", "").strip()
        except:
            return "[Joe is offline]"

    def inline_quote(self, finding_type: str, value: str, platform: str = "", context: str = "") -> str:
        prompt = f"Finding: {finding_type} — {value}" + (f" on {platform}" if platform else "") + "\nOne short observation."
        # Non-streaming for small quotes
        return "".join(list(self.stream_chat(prompt, JOE_SYSTEM, max_tokens=60)))

    def chat(self, question: str) -> str:
        return "".join(list(self.stream_chat(question, JOE_SYSTEM, max_tokens=1000)))

    def answer(self, question: str, target: Target, history: List[Dict]) -> str:
        history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-6:])
        context = f"Investigation: {target.primary}\nRecent conversation:\n{history_text}"
        prompt = f"{context}\n\nUser asked: {question}"
        return "".join(list(self.stream_chat(prompt, JOE_SYSTEM, max_tokens=1000)))