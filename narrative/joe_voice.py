# narrative/joe_voice.py
import httpx
import json
from typing import List, Dict, Optional
from core.target_model import Target

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "mistral:7b-instruct"

JOE_SYSTEM = """You are Joe Goldberg — the investigator, not the murderer.
You are precise, obsessive, and speak in short punchy sentences.
Inner monologue style. Present tense. Never clinical.
Refer to targets by first name. Never say "I found" — say "I know", "I notice".
Keep responses SHORT — 3 to 5 sentences max unless doing a closing monologue.
No markdown. No bullet points. Just raw thought."""

JOE_MONOLOGUE_SYSTEM = """You are Joe Goldberg — the investigator.
You have just completed an OSINT investigation. Write a closing monologue.
4 to 6 paragraphs. Intimate. Obsessive. Connect the dots like a person, not a report.
End with one quiet unsettling observation. No markdown."""


class JoeVoice:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = httpx.Client(timeout=30)

    def _ask(self, prompt: str, context: str = "", monologue: bool = False) -> str:
        system = JOE_MONOLOGUE_SYSTEM if monologue else JOE_SYSTEM
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        try:
            r = self.client.post(
                OLLAMA_URL,
                json={
                    "model": self.model,
                    "system": system,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.75,
                        "top_p": 0.85,
                        "num_predict": 120,   # short answers fast
                        "num_ctx": 1024,      # smaller context = faster
                        "repeat_penalty": 1.1,
                    },
                },
            )
            return r.json().get("response", "").strip()
        except Exception as e:
            return f"[offline: {e}]"

    def inline_quote(self, finding_type: str, value: str, platform: str = "", context: str = "") -> str:
        prompt = (
            f"Finding: {finding_type} — {value}"
            + (f" on {platform}" if platform else "")
            + "\nOne observation. Max 15 words. No quotes needed."
        )
        return self._ask(prompt, context)

    def closing_monologue(self, target: Target, session_context: str = "") -> str:
        findings = self._build_findings_summary(target)
        prompt = (
            f"Target: {target.primary} ({target.target_type})\n\n"
            f"Findings:\n{findings}\n\n"
            f"Write the closing monologue."
        )
        # Monologue gets more tokens
        try:
            r = self.client.post(
                OLLAMA_URL,
                json={
                    "model": self.model,
                    "system": JOE_MONOLOGUE_SYSTEM,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.85,
                        "top_p": 0.9,
                        "num_predict": 350,
                        "num_ctx": 2048,
                        "repeat_penalty": 1.1,
                    },
                },
                timeout=90,
            )
            return r.json().get("response", "").strip()
        except Exception as e:
            return f"[joe is thinking... try again: {e}]"

    def answer(self, question: str, target: Target, history: List[Dict]) -> str:
        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in history[-6:]   # only last 6 turns — keeps context small
        )
        findings = self._build_findings_summary(target)
        context = (
            f"Investigation: {target.primary}\n"
            f"Findings:\n{findings}\n\n"
            f"Recent conversation:\n{history_text}"
        )
        return self._ask(question, context)

    def chat(self, question: str) -> str:
        """Answer without any investigation context — for freeform chat."""
        return self._ask(question)

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