import os
import json
import time

MEMORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "soldierboy_memory.json")
LEGACY_MEMORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "joe_memory.json")

class SoldierBoyMemory:
    def __init__(self, filepath=MEMORY_FILE_PATH):
        if not os.path.exists(filepath) and os.path.exists(LEGACY_MEMORY_FILE_PATH):
            self.filepath = LEGACY_MEMORY_FILE_PATH
        else:
            self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            initial = {
                "user_speech_patterns": [
                    "User prefers concise, witty, energetic voice responses.",
                    "STT mishears 'Dean' or 'Soldier' as 'joke', 'joh', 'zho', 'jarvis', 'chow', 'show'."
                ],
                "failures_and_lessons": [
                    "Speech recognition of target usernames is error-prone; trigger target dialog modal when intent is 'investigate' without clean target."
                ],
                "learned_skills": [
                    {
                        "name": "open_app",
                        "description": "Launch desktop applications (browser, terminal, editor, etc.)",
                        "trigger": "open app"
                    },
                    {
                        "name": "google_search",
                        "description": "Search Google in default browser",
                        "trigger": "google search"
                    }
                ],
                "history_log": []
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(initial, f, indent=2)

    def load_memory(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[SoldierBoyMemory] Error loading memory: {e}")
            return {}

    def log_speech_pattern(self, note: str):
        mem = self.load_memory()
        patterns = mem.setdefault("user_speech_patterns", [])
        if note not in patterns:
            patterns.append(note)
            self._save(mem)

    def log_failure_lesson(self, failure_and_lesson: str):
        mem = self.load_memory()
        lessons = mem.setdefault("failures_and_lessons", [])
        if failure_and_lesson not in lessons:
            lessons.append(failure_and_lesson)
            self._save(mem)

    def register_learned_skill(self, skill_name: str, description: str, trigger: str, code_snippet: str = ""):
        mem = self.load_memory()
        skills = mem.setdefault("learned_skills", [])
        # Check if already exists
        for s in skills:
            if s.get("name") == skill_name:
                s["description"] = description
                s["trigger"] = trigger
                if code_snippet:
                    s["code"] = code_snippet
                self._save(mem)
                return
        skills.append({
            "name": skill_name,
            "description": description,
            "trigger": trigger,
            "code": code_snippet,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save(mem)

    def get_memory_summary_for_prompt(self):
        mem = self.load_memory()
        patterns = "\n- ".join(mem.get("user_speech_patterns", [])[-4:])
        lessons = "\n- ".join(mem.get("failures_and_lessons", [])[-4:])
        skills = ", ".join([s["name"] for s in mem.get("learned_skills", [])])
        return f"""PERSISTENT MEMORY & LEARNED SKILLS:
- User Speech Habits:\n- {patterns}
- Learned Lessons & Fixes:\n- {lessons}
- Available Learned Skills: {skills}"""

    def _save(self, data):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[SoldierBoyMemory] Error saving memory: {e}")
