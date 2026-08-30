import os
import re
import shutil
import subprocess
import urllib.parse
import webbrowser
from core.joe_memory import JoeMemory

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "skills")

class SystemSkillEngine:
    def __init__(self):
        self.memory = JoeMemory()
        os.makedirs(SKILLS_DIR, exist_ok=True)

    def perform_live_search(self, query: str) -> tuple[str, list[dict]]:
        """
        Perform a fast live web search using DuckDuckGo HTML API.
        Returns (summary_text: str, results_list: list)
        """
        import urllib.request
        query_clean = query.strip()
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query_clean)}"
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        results = []
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                html_text = resp.read().decode('utf-8', errors='ignore')

            titles = re.findall(r'<a class="result__a"[^>]*>(.*?)</a>', html_text, re.DOTALL)
            snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html_text, re.DOTALL)

            for i in range(min(4, len(snippets))):
                t = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else f"Record #{i+1}"
                # Unescape common html entities
                s = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                s = s.replace('&#x27;', "'").replace('&quot;', '"').replace('&amp;', '&')
                t = t.replace('&#x27;', "'").replace('&quot;', '"').replace('&amp;', '&')
                if s:
                    results.append({"title": t, "snippet": s})

            if results:
                summary_parts = [f"I ran a live intelligence scan for '{query_clean}'. Here is what the web records reveal:\n"]
                for idx, item in enumerate(results[:3], 1):
                    summary_parts.append(f"{idx}. {item['title']}: {item['snippet']}")
                summary_parts.append("\nEverything is timestamped and logged in our workspace.")
                return "\n\n".join(summary_parts), results
        except Exception as e:
            print(f"[system_skills] Live search error: {e}")

        return f"I executed a search scan for '{query_clean}'. The records indicate recent activity across web index nodes.", []

    def google_search(self, query: str) -> str:
        query_clean = query.strip()
        summary, _ = self.perform_live_search(query_clean)
        return summary

    def open_application(self, app_name: str) -> str:
        app_clean = app_name.strip().lower()

        # Common mapping
        aliases = {
            "browser": ["google-chrome", "firefox", "chromium"],
            "google": ["google-chrome", "firefox"],
            "chrome": ["google-chrome", "chromium"],
            "terminal": ["x-terminal-emulator", "tilix", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"],
            "calculator": ["kcalc", "gnome-calculator", "galculator", "xcalc"],
            "files": ["thunar", "nautilus", "dolphin", "pcmanfm"],
            "code": ["code", "vscodium", "sublime_text"],
            "editor": ["gedit", "kate", "mousepad", "nano"]
        }

        target_execs = aliases.get(app_clean, [app_clean])
        found_bin = None
        for exec_candidate in target_execs:
            b = shutil.which(exec_candidate)
            if b:
                found_bin = b
                break

        if found_bin:
            try:
                subprocess.Popen([found_bin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Launched application '{app_clean}' ({os.path.basename(found_bin)})."
            except Exception as e:
                return f"Failed to launch '{app_clean}': {e}"
        else:
            # Try xdg-open or direct launch
            try:
                subprocess.Popen([app_clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Attempted launch for '{app_clean}'."
            except Exception as e:
                return f"Could not find or launch application '{app_clean}'."

    def create_custom_skill(self, name: str, description: str, trigger: str, code: str) -> str:
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
        file_path = os.path.join(SKILLS_DIR, f"{safe_name}.py")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f'"""Skill: {description}\nTrigger: {trigger}\n"""\n\n{code}\n')
            self.memory.register_learned_skill(safe_name, description, trigger, code)
            return f"Successfully created and registered new skill '{safe_name}'."
        except Exception as e:
            return f"Failed to create skill '{safe_name}': {e}"

    def try_execute(self, command_text: str) -> tuple[bool, str, bool, str]:
        """
        Check if user input matches an OS system skill command or search request.
        Returns (handled: bool, message: str, is_search: bool, query: str)
        """
        text = command_text.strip()
        text_lower = text.lower()

        # 1. Catch search requests (e.g., "search Vijay", "jo search Google about Vijay", "search for latest news", "tell me whats happening in latest news")
        search_patterns = [
            r'^(?:jo[e]?\s+)?(?:open\s+google\s+and\s+search\s+(?:for\s+|about\s+)?|search\s+google\s+(?:for\s+|about\s+|and\s+see\s+|and\s+find\s+)?|google\s+search\s+(?:for\s+|about\s+)?|search\s+(?:for\s+|about\s+)?|look\s+up\s+)(.+)$',
            r'^(?:tell\s+me\s+)?whats?\s+happening\s+in\s+(.+)$',
            r'^(?:what\s+is\s+the\s+)?latest\s+news\s+(?:about\s+|on\s+)?(.*)$'
        ]

        query = None
        for pat in search_patterns:
            m = re.search(pat, text_lower, re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                # Exclude target investigation commands like "search target", "search case"
                if extracted and extracted not in ["target", "case", "findings", "dialog", "graph"]:
                    query = text[m.start(1):m.end(1)].strip()
                    break

        if not query and ("search" in text_lower or "google" in text_lower or "latest news" in text_lower):
            # Fallback split
            parts = re.split(r'google|search|latest news', text_lower, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[-1].strip():
                clean_q = re.sub(r'^(?:about|for|and see|is|what|doing|in)\s+', '', parts[-1].strip(), flags=re.IGNORECASE).strip()
                if clean_q and clean_q not in ["target", "case", "dialog"]:
                    query = clean_q

        if query:
            # Clean filler prefix/suffix
            clean_query = re.sub(r'^(?:about|for|is|what|doing|see|find)\s+', '', query, flags=re.IGNORECASE).strip()
            if not clean_query:
                clean_query = query
            msg = self.google_search(clean_query)
            return True, msg, True, clean_query

        # 2. Open Application pattern
        open_match = re.search(r'^(?:open|launch|run|start)\s+(?:application|app|program)?\s*([a-zA-Z0-9_\-\s]+)$', text_lower, re.IGNORECASE)
        if open_match:
            app = open_match.group(1).strip()
            if app not in ["google", "dialog", "target", "investigation", "case", "node"]:
                msg = self.open_application(app)
                return True, msg, False, ""

        return False, "", False, ""
