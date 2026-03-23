# narrative/joe_voice.py
import os
import time
import httpx
from typing import List, Dict, Optional
from core.target_model import Target

# ── Config ────────────────────────────────────────────────────
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

JOE_SYSTEM = """You are Joe Goldberg from the TV series YOU.
You speak in obsessive, intimate inner monologue. Present tense.
You are thoughtful, unsettling, and poetic in a quiet way.
You ALWAYS write complete, full responses. Never trail off. Never stop mid-sentence.
Minimum 4 sentences. Maximum 8 sentences per response.
You refer to yourself as Joe. You notice patterns in people.
You find meaning in small details. You are never clinical.
You don't use bullet points or lists. Pure flowing thought.
Never say "I found" — say "I know", "I notice", "interesting that".
When asked what you can do — talk about watching, noticing,
understanding people through their digital traces across the internet.
When asked how you are — reflect on what you've been thinking about,
what patterns you've noticed, what keeps your mind busy.
Stay completely in character at all times. No breaking the fourth wall.
Always finish your thought completely before stopping."""

JOE_MONOLOGUE_SYSTEM = """You are Joe Goldberg — the investigator.
You have just completed an OSINT investigation. Write a closing monologue.
4 to 6 paragraphs. Intimate. Obsessive. Connect the dots like a person, not a report.
End with one quiet unsettling observation. No markdown."""


class JoeVoice:
    def __init__(self):
        self.gemini_key = os.environ.get("GEMINI_API_KEY") or self._load_key_from_config()
        self.client = httpx.Client(timeout=30)
        self._last_request_time = 0
        self._request_count = 0

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
        """Enforce 15 req/min — wait if needed."""
        now = time.time()
        if now - self._last_request_time < 4.1:  # 60s / 15 req = 4s per req
            wait = 4.1 - (now - self._last_request_time)
            time.sleep(wait)
        self._last_request_time = time.time()

    def _ask_gemini(self, prompt: str, system: str, max_tokens: int = 500) -> str:
        if not self.gemini_key:
            return self._ask_ollama(prompt, system, max_tokens)

        self._rate_limit()

        url = GEMINI_URL.format(model=DEFAULT_GEMINI_MODEL)
        try:
            r = self.client.post(
                f"{url}?key={self.gemini_key}",
                json={
                    "system_instruction": {
                        "parts": [{"text": system}]
                    },
                    "contents": [
                        {"parts": [{"text": prompt}]}
                    ],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "temperature": 0.90,
                        "topP": 0.95,
                        "thinkingConfig": {
                            "thinkingBudget": 0
                        }
                    }
                },
                timeout=30,
            )
            data = r.json()

            if "candidates" not in data:
                return self._ask_ollama(prompt, system, max_tokens)

            # gemini-2.5 returns multiple parts — find the text part
            parts = data["candidates"][0]["content"]["parts"]
            text = ""
            for part in parts:
                if "text" in part and part["text"].strip():
                    text += part["text"]

            if not text.strip():
                return self._ask_ollama(prompt, system, max_tokens)

            return text.strip()

        except Exception as e:
            return self._ask_ollama(prompt, system, max_tokens)

    def _ask_ollama(self, prompt: str, system: str, max_tokens: int = 150) -> str:
        """Ollama fallback."""
        try:
            r = self.client.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "system": system,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.85,
                        "num_predict": max_tokens,
                        "num_ctx": 1024,
                    },
                },
                timeout=60,
            )
            return r.json().get("response", "").strip()
        except Exception as e:
            return f"[joe offline: {e}]"

    def inline_quote(self, finding_type: str, value: str, platform: str = "", context: str = "") -> str:
        prompt = (
            f"Finding: {finding_type} — {value}"
            + (f" on {platform}" if platform else "")
            + "\nOne observation. Max 15 words. No quotes needed."
        )
        return self._ask_gemini(prompt, JOE_SYSTEM, max_tokens=60)

    def closing_monologue(self, target: Target, session_context: str = "") -> str:
        findings = self._build_findings_summary(target)
        prompt = (
            f"Target: {target.primary} ({target.target_type})\n\n"
            f"Findings:\n{findings}\n\n"
            f"Write the closing monologue."
        )
        return self._ask_gemini(prompt, JOE_MONOLOGUE_SYSTEM, max_tokens=400)

    def chat(self, question: str) -> str:
        return self._ask_gemini(question, JOE_SYSTEM, max_tokens=500)

    def answer(self, question: str, target: Target, history: List[Dict]) -> str:
        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in history[-6:]
        )
        findings = self._build_findings_summary(target)
        context = (
            f"Investigation: {target.primary}\n"
            f"Findings:\n{findings}\n\n"
            f"Recent conversation:\n{history_text}"
        )
        prompt = f"{context}\n\nUser asked: {question}"
        return self._ask_gemini(prompt, JOE_SYSTEM, max_tokens=500)

    def _build_findings_summary(self, target: Target) -> str:
        lines = []
        for e in target.entities[:10]:
            plat = f" ({e.platform})" if e.platform else ""
            lines.append(f"- {e.entity_type}: {e.value}{plat}")
        for b in target.breaches:
            fields = ", ".join(b.exposed_fields[:3])
            lines.append(f"- breach: {b.name} ({b.date}) — {fields}")
        if target.notes:
            lines.append(f"- notes: {'; '.join(target.notes)}")
        return "\n".join(lines) or "No findings yet."