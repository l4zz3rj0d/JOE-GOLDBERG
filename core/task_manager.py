import threading
import time
from typing import Dict, List, Optional, Any
from core.task import Task, TaskState, TaskType, TaskFinding
from core.event_bus import get_event_bus

class TaskManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TaskManager, cls).__new__(cls)
                cls._instance._tasks: Dict[str, Task] = {}
                cls._instance._active_task_id: Optional[str] = None
                cls._instance._bus = get_event_bus()
            return cls._instance

    def create_task(self, type_: str, title: str, data: Optional[Dict[str, Any]] = None) -> Task:
        with self._lock:
            task = Task(type=type_, title=title, data=data or {})
            self._tasks[task.task_id] = task
            self._active_task_id = task.task_id

        payload = {"task": task.to_dict()}
        self._bus.emit("task.created", payload)
        self.update_state(task.task_id, TaskState.RUNNING.value, "Task started...")
        return task

    def update_state(self, task_id: str, state: str, message: str = ""):
        task = self.get_task(task_id)
        if not task:
            return
        with self._lock:
            task.state = state
            task.updated_at = time.time()
            if message:
                task.progress_msg = message

        payload = {"task_id": task_id, "state": state, "message": message, "task": task.to_dict()}
        self._bus.emit("task.started" if state == TaskState.RUNNING.value else "task.updated", payload)

    def update_progress(self, task_id: str, progress_pct: int, message: str):
        task = self.get_task(task_id)
        if not task:
            return
        with self._lock:
            task.progress_pct = max(0, min(100, progress_pct))
            task.progress_msg = message
            task.updated_at = time.time()

        payload = {
            "task_id": task_id,
            "progress": task.progress_pct,
            "message": message,
            "task": task.to_dict()
        }
        self._bus.emit("task.progress", payload)

    def add_finding(self, task_id: str, finding: TaskFinding):
        task = self.get_task(task_id)
        if not task:
            return
        with self._lock:
            task.findings.append(finding)
            task.updated_at = time.time()

        payload = {
            "task_id": task_id,
            "finding": finding.to_dict(),
            "findings_count": len(task.findings),
            "task": task.to_dict()
        }
        self._bus.emit("task.finding", payload)

    def complete_task(self, task_id: str, summary: str = "", extra_data: Optional[Dict[str, Any]] = None):
        task = self.get_task(task_id)
        if not task:
            return
        with self._lock:
            task.state = TaskState.COMPLETED.value
            task.summary = summary or f"{len(task.findings)} items returned"
            task.progress_pct = 100
            task.updated_at = time.time()
            if extra_data:
                task.data.update(extra_data)

        payload = {
            "task_id": task_id,
            "summary": task.summary,
            "task": task.to_dict()
        }
        self._bus.emit("task.completed", payload)

    def fail_task(self, task_id: str, error_msg: str):
        task = self.get_task(task_id)
        if not task:
            return
        with self._lock:
            task.state = TaskState.FAILED.value
            task.summary = f"Failed: {error_msg}"
            task.updated_at = time.time()

        payload = {
            "task_id": task_id,
            "error": error_msg,
            "task": task.to_dict()
        }
        self._bus.emit("task.failed", payload)

    def minimize_task(self, task_id: Optional[str] = None):
        target_id = task_id or self._active_task_id
        if not target_id:
            return
        task = self.get_task(target_id)
        if not task:
            return
        with self._lock:
            task.is_minimized = True
            task.state = TaskState.MINIMIZED.value
            task.updated_at = time.time()

        payload = {"task_id": target_id, "task": task.to_dict()}
        self._bus.emit("task.minimized", payload)

    def expand_task(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return
        with self._lock:
            task.is_minimized = False
            task.state = TaskState.RUNNING.value if task.progress_pct < 100 else TaskState.COMPLETED.value
            task.updated_at = time.time()
            self._active_task_id = task_id

        payload = {"task_id": task_id, "task": task.to_dict()}
        self._bus.emit("task.maximized", payload)

    def close_task(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return
        with self._lock:
            if self._active_task_id == task_id:
                self._active_task_id = None
            if task_id in self._tasks:
                del self._tasks[task_id]

        payload = {"task_id": task_id}
        self._bus.emit("task.closed", payload)

    def select_task_item(self, task_id: str, index: int) -> Optional[TaskFinding]:
        task = self.get_task(task_id)
        if not task or not (0 <= index < len(task.findings)):
            return None
        with self._lock:
            task.selected_index = index
            task.updated_at = time.time()
            finding = task.findings[index]

        payload = {
            "task_id": task_id,
            "selected_index": index,
            "finding": finding.to_dict(),
            "task": task.to_dict()
        }
        self._bus.emit("task.updated", payload)
        return finding

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_active_task(self) -> Optional[Task]:
        with self._lock:
            if self._active_task_id:
                return self._tasks.get(self._active_task_id)
            return None

    def list_tasks(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())

def get_task_manager() -> TaskManager:
    return TaskManager()
