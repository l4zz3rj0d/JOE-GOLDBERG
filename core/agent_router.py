import re
from typing import Tuple, Dict, Any, Optional
from core.task import Task, TaskType, TaskFinding
from core.task_manager import get_task_manager, TaskManager

class AgentRouter:
    def __init__(self):
        self.task_manager: TaskManager = get_task_manager()

    def route_input(self, text: str) -> Tuple[bool, str, Optional[Task], str]:
        """
        Routes incoming user voice/text query.
        Returns tuple:
            (handled: bool, spoken_ack: str, task: Optional[Task], action_category: str)
        """
        text_strip = text.strip()
        text_lower = text_strip.lower()
        if not text_lower:
            return False, "", None, ""

        active_task = self.task_manager.get_active_task()

        # ── 1. Check for Conversational Follow-Up Commands ────────
        # A. Minimize command
        if any(w in text_lower for w in ["minimize", "minimize panel", "hide panel", "minimize that", "hide that", "put it down"]):
            if active_task:
                self.task_manager.minimize_task(active_task.task_id)
                return True, "Minimized the panel, buddy.", active_task, "followup_minimize"

        # B. Expand/Maximize command
        if any(w in text_lower for w in ["expand", "maximize", "show panel", "restore panel", "bring it up", "open panel", "restore", "restore surface", "expand surface", "restore task"]):
            if active_task:
                self.task_manager.expand_task(active_task.task_id)
                return True, "Expanded the task surface.", active_task, "followup_expand"

        # C. Close/Dismiss command
        if any(w in text_lower for w in ["close panel", "close task", "dismiss panel", "dismiss task", "close that", "dismiss that"]):
            if active_task:
                self.task_manager.close_task(active_task.task_id)
                return True, "Closed the task surface.", None, "followup_close"

        # D. Select Item / Open Result ("open the second one", "show result 1")
        m_item = re.search(r'(?:open|show|play|view|select|click)\s+(?:the\s+)?(?:result\s+|video\s+|item\s+|link\s+|number\s+)?(\d+|first|second|third|fourth|fifth)', text_lower)
        if m_item and active_task and active_task.findings:
            raw_idx = m_item.group(1)
            idx_map = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
            idx_num = idx_map.get(raw_idx, int(raw_idx) if raw_idx.isdigit() else 1) - 1
            
            finding = self.task_manager.select_task_item(active_task.task_id, idx_num)
            if finding:
                # Upgrade task to Internal Browser Surface for watching/viewing
                surf_task = self.task_manager.create_task(
                    type_=TaskType.BROWSER_SURF.value,
                    title=f"Browser: {finding.title[:35]}",
                    data={"url": finding.url, "parent_task_id": active_task.task_id, "title": finding.title}
                )
                self.task_manager.add_finding(surf_task.task_id, finding)
                self.task_manager.complete_task(surf_task.task_id, f"Loaded internal surface: {finding.title}")
                return True, f"Opening {finding.title} inside the internal browser surface.", surf_task, "followup_select"

        # ── 2. Check for YouTube Search ────────────────────────────
        if "youtube" in text_lower or "watch" in text_lower or "video search" in text_lower:
            m_yt = re.search(r'(?:search\s+youtube\s+for|youtube\s+search|youtube|find\s+videos?\s+on|watch)\s+(?:for\s+)?(.+)', text_lower)
            query = m_yt.group(1).strip() if m_yt else text_strip
            query = re.sub(r'^(?:do\s+a|can\s+you|please|search|for|about)\s+', '', query, flags=re.IGNORECASE).strip()
            if not query:
                query = text_strip

            task = self.task_manager.create_task(
                type_=TaskType.YOUTUBE_SEARCH.value,
                title=f"YouTube Search: {query}",
                data={"query": query}
            )
            return True, f"Searching YouTube for '{query}', buddy.", task, "youtube_search"

        # ── 3. Check for Google / Web Search ───────────────────────
        if any(kw in text_lower for kw in ["google", "search", "look up", "latest news", "find out"]):
            if not any(t_kw in text_lower for t_kw in ["search target", "search case", "target investigation"]):
                m_g = re.search(r'(?:google\s+search|search\s+google|search|look\s+up|find\s+out|find)\s+(?:for\s+|about\s+|on\s+)?(.+)', text_lower)
                query = m_g.group(1).strip() if m_g else text_strip
                query = re.sub(r'^(?:do\s+a|can\s+you|please|search|for|about)\s+', '', query, flags=re.IGNORECASE).strip()
                if not query:
                    query = text_strip

                task = self.task_manager.create_task(
                    type_=TaskType.GOOGLE_SEARCH.value,
                    title=f"Google Search: {query}",
                    data={"query": query}
                )
                return True, f"Searching Google for '{query}'.", task, "google_search"

        # ── 4. Check for System Action (App Launch) ────────────────
        m_app = re.search(r'^(?:open|launch|run|start)\s+(?:application|app|program)?\s*([a-zA-Z0-9_\-\s]+)$', text_lower)
        if m_app:
            app_name = m_app.group(1).strip()
            excluded = ["google", "youtube", "dialog", "target", "investigation", "case", "node", "first", "second", "third", "fourth", "fifth", "1", "2", "3", "4", "5", "panel", "surface", "chip"]
            if app_name not in excluded and not app_name.startswith("the ") and not any(w in app_name for w in ["result", "video", "item", "link", "number", "second", "third", "fourth", "fifth"]):
                task = self.task_manager.create_task(
                    type_=TaskType.SYSTEM_ACTION.value,
                    title=f"System Action: Launch {app_name.upper()}",
                    data={"app_name": app_name}
                )
                return True, f"Launching {app_name} on your system.", task, "system_action"

        # ── 5. Check for Memory Recall Query ───────────────────────
        if any(kw in text_lower for kw in ["remember", "yesterday", "previous conversation", "what did we say", "what did we discuss"]):
            task = self.task_manager.create_task(
                type_=TaskType.MEMORY_RECALL.value,
                title=f"Memory Recall: {text_strip[:30]}",
                data={"query": text_strip}
            )
            return True, "Scanning memory logs for related context.", task, "memory_recall"

        # ── 6. Check for Investigation Recon ─────────────────────
        if any(kw in text_lower for kw in ["investigate", "scan target", "recon case", "analyze target"]):
            m_target = re.search(r'(?:investigate|scan|recon|analyze)\s+(?:target\s+|domain\s+)?([a-zA-Z0-9\.\-_]+)', text_lower)
            target = m_target.group(1).strip() if m_target else "target"
            task = self.task_manager.create_task(
                type_=TaskType.INVESTIGATION.value,
                title=f"Investigation: {target}",
                data={"target": target}
            )
            return True, f"Initiating investigation pipeline for target '{target}'.", task, "investigation"

        return False, "", None, ""
