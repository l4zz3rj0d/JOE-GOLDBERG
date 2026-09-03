# core/target_model.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import re

PROJECT_ROOT = Path(__file__).parent.parent
CASES_DIR = PROJECT_ROOT / "cases"
CASES_DIR.mkdir(exist_ok=True)


def clean_duplicate_suffix(val: str) -> str:
    """Cleans duplicated TLD/suffix from a domain or email (e.g. gmail.com.com -> gmail.com)."""
    if not val:
        return val
    while True:
        match = re.search(r"\.([a-zA-Z]{2,})\.\1$", val, re.IGNORECASE)
        if match:
            tld = match.group(1)
            val = val[:-len(tld) - 1]
        else:
            break
    return val


@dataclass
class Entity:
    entity_type: str
    value: str
    sources: List[str]
    confidence: float
    platform: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    discovered_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )

    @property
    def entity_id(self) -> str:
        plat = self.platform or "api"
        clean_val = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(self.value).lower())
        return f"{self.entity_type}_{clean_val}_{plat.lower()}"



@dataclass
class Breach:
    name: str
    date: str
    exposed_fields: List[str]
    source: str
    verified: bool = False


@dataclass
class Target:
    primary: str
    target_type: str
    opened_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    entities: List[Entity] = field(default_factory=list)
    breaches: List[Breach] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    timeline: List[Dict] = field(default_factory=list)
    risk_score: float = 0.0

    def add_entity(self, entity: Entity) -> bool:
        """Add entity — deduplicate by value + platform combination."""
        entity.value = clean_duplicate_suffix(entity.value.strip().rstrip('.'))
        for e in self.entities:
            e.value = clean_duplicate_suffix(e.value.strip().rstrip('.'))
            if (e.value == entity.value and
                e.entity_type == entity.entity_type and
                e.platform == entity.platform):
                # Exact duplicate — merge sources only
                e.sources = list(set(e.sources + entity.sources))
                e.confidence = max(e.confidence, entity.confidence)
                if entity.metadata:
                    if not e.metadata:
                        e.metadata = {}
                    for k, v in entity.metadata.items():
                        if v is not None and v != "":
                            if k == "related_to" and isinstance(e.metadata.get("related_to"), dict) and isinstance(v, dict):
                                for sub_k, sub_v in v.items():
                                    if sub_v:
                                        e.metadata["related_to"][sub_k] = sub_v
                            elif not e.metadata.get(k):
                                e.metadata[k] = v
                return False
        # New entity or same value on different platform
        self.entities.append(entity)
        self.log("entity_found", {"type": entity.entity_type, "value": entity.value})
        return True

    def add_breach(self, breach: Breach) -> bool:
        if not any(b.name == breach.name for b in self.breaches):
            self.breaches.append(breach)
            self.log("breach_found", {"name": breach.name})
            return True
        return False

    def log(self, event: str, data: Dict = None):
        self.timeline.append({
            "event": event,
            "data": data or {},
            "at": datetime.now().isoformat(),
        })
        self.last_updated = datetime.now().isoformat()

    def compute_risk(self) -> float:
        score = 0.0
        score += min(0.5, len(self.breaches) * 0.15)
        score += min(0.3, len(self.entities) * 0.04)
        score += 0.2 if any(
            "password" in " ".join(b.exposed_fields).lower()
            for b in self.breaches
        ) else 0.0
        self.risk_score = round(min(1.0, score), 2)
        return self.risk_score

    @property
    def case_slug(self) -> str:
        return self.primary.replace("@", "_").replace(".", "_").replace(" ", "_")

    def to_dict(self) -> Dict:
        return {
            "primary": self.primary,
            "target_type": self.target_type,
            "opened_at": self.opened_at,
            "last_updated": self.last_updated,
            "risk_score": self.risk_score,
            "entities": [e.__dict__ for e in self.entities],
            "breaches": [b.__dict__ for b in self.breaches],
            "notes": self.notes,
            "timeline": self.timeline,
        }

    def save(self, cases_dir: Path = CASES_DIR):
        folder = cases_dir / self.case_slug
        folder.mkdir(parents=True, exist_ok=True)
        self.compute_risk()
        (folder / "case.json").write_text(
            json.dumps(self.to_dict(), indent=2)
        )
        return folder

    @classmethod
    def load(cls, target: str, cases_dir: Path = CASES_DIR):
        # We slugify target directly
        slug = target.replace("@", "_").replace(".", "_").replace(" ", "_")
        path = cases_dir / slug / "case.json"
        if not path.exists():
            for case_file in cases_dir.glob("*/case.json"):
                try:
                    data = json.loads(case_file.read_text())
                    if data["primary"] == target:
                        path = case_file
                        break
                except:
                    pass
        if not path.exists():
            raise FileNotFoundError(f"No case found for: {target}")
        data = json.loads(path.read_text())
        t = cls(primary=data["primary"], target_type=data["target_type"])
        t.opened_at = data["opened_at"]
        t.risk_score = data["risk_score"]
        t.notes = data["notes"]
        t.timeline = data["timeline"]
        t.entities = [Entity(**e) for e in data["entities"]]
        t.breaches = [Breach(**b) for b in data["breaches"]]
        return t