# Manages full conversation history per investigation session
from typing import List, Dict
from datetime import datetime


class SessionMemory:
    def __init__(self):
        self.history: List[Dict] = []
        self.started_at = datetime.now().isoformat()

    def add(self, role: str, content: str):
        """Append a message. role = 'user' | 'joe'"""
        self.history.append({
            "role": role,
            "content": content,
            "at": datetime.now().isoformat(),
        })

    def last_n(self, n: int = 12) -> List[Dict]:
        return self.history[-n:]

    def clear(self):
        self.history = []

    def to_text(self, n: int = 12) -> str:
        return "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in self.last_n(n)
        )