"""
Resource registry — real, located, user-owned inventory (replaces the old
fictional flat inventory.json).

Every resource is an explicit record with a **location**, owner and provenance,
and is fully editable / deletable through the API and UI. Nothing is fabricated:
the seed entries are placed at real UN Humanitarian Response Depot (UNHRD)
locations and clearly marked ``source: "example"`` so the user can edit or delete
them and enter their own real stock.
"""
from __future__ import annotations
import os
import json
import time
import threading
import uuid
from typing import List, Dict, Optional, Any

from pydantic import BaseModel, Field

_FILE = os.path.join(os.path.dirname(__file__), "..", "resources.json")
_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Resource(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: str = "supplies"          # canonical key used by the logistics agent
    label: str = ""                 # human-readable name
    quantity: int = 0
    unit: str = "units"
    lat: Optional[float] = None
    lon: Optional[float] = None
    location: str = ""              # place name of the stockpile
    owner: str = ""                 # holding organisation
    source: str = "user"           # provenance: user | example | import
    updated_at: str = Field(default_factory=_now)


# Seed at REAL UNHRD depot locations; marked "example" and fully editable.
_SEED: List[Dict[str, Any]] = [
    {"type": "medics", "label": "Medical personnel", "quantity": 30, "unit": "personnel",
     "location": "UNHRD Brindisi (IT)", "lat": 40.6453, "lon": 17.9461, "owner": "WHO/WFP"},
    {"type": "water", "label": "Drinking water", "quantity": 5000, "unit": "litres",
     "location": "UNHRD Brindisi (IT)", "lat": 40.6453, "lon": 17.9461, "owner": "UNICEF"},
    {"type": "tents", "label": "Family tents", "quantity": 800, "unit": "units",
     "location": "UNHRD Dubai (AE)", "lat": 25.2048, "lon": 55.2708, "owner": "IFRC"},
    {"type": "water", "label": "Drinking water", "quantity": 4000, "unit": "litres",
     "location": "UNHRD Dubai (AE)", "lat": 25.2048, "lon": 55.2708, "owner": "UNICEF"},
    {"type": "food_rations", "label": "Food rations", "quantity": 6000, "unit": "rations",
     "location": "UNHRD Accra (GH)", "lat": 5.6037, "lon": -0.187, "owner": "WFP"},
    {"type": "rescue_teams", "label": "USAR teams", "quantity": 6, "unit": "teams",
     "location": "UNHRD Subang (MY)", "lat": 3.0738, "lon": 101.5183, "owner": "INSARAG"},
    {"type": "rescue_boats", "label": "Rescue boats", "quantity": 20, "unit": "boats",
     "location": "UNHRD Panama City", "lat": 8.9824, "lon": -79.5199, "owner": "IFRC"},
    {"type": "tarpaulins", "label": "Tarpaulins / shelter kits", "quantity": 2000, "unit": "units",
     "location": "UNHRD Panama City", "lat": 8.9824, "lon": -79.5199, "owner": "UNHCR"},
    {"type": "generators", "label": "Generators", "quantity": 25, "unit": "units",
     "location": "UNHRD Brindisi (IT)", "lat": 40.6453, "lon": 17.9461, "owner": "WFP"},
]


class ResourceStore:
    def __init__(self):
        self._items: List[Resource] = []
        self._load()

    def _load(self):
        if os.path.exists(_FILE):
            try:
                with open(_FILE, "r", encoding="utf-8") as f:
                    self._items = [Resource(**r) for r in json.load(f)]
                return
            except Exception:
                pass
        # first run — seed and persist
        self._items = [Resource(source="example", **s) for s in _SEED]
        self._save()

    def _save(self):
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self._items], f, indent=2)

    def all(self) -> List[Resource]:
        return list(self._items)

    def create(self, data: Dict[str, Any]) -> Resource:
        with _LOCK:
            r = Resource(**{**data, "updated_at": _now()})
            self._items.append(r)
            self._save()
            return r

    def update(self, rid: str, data: Dict[str, Any]) -> Optional[Resource]:
        with _LOCK:
            for i, r in enumerate(self._items):
                if r.id == rid:
                    merged = {**r.model_dump(), **{k: v for k, v in data.items() if v is not None},
                              "id": rid, "updated_at": _now()}
                    self._items[i] = Resource(**merged)
                    self._save()
                    return self._items[i]
            return None

    def delete(self, rid: str) -> bool:
        with _LOCK:
            before = len(self._items)
            self._items = [r for r in self._items if r.id != rid]
            if len(self._items) < before:
                self._save()
                return True
            return False

    # ---- aggregate views used by the logistics agent ----
    def totals_by_type(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in self._items:
            out[r.type] = out.get(r.type, 0) + max(0, r.quantity)
        return out

    def locations_for(self, rtype: str) -> List[Resource]:
        return [r for r in self._items if r.type == rtype and r.quantity > 0]

    def consume(self, rtype: str, qty: int) -> int:
        """Deduct qty of a type across locations (nearest-agnostic, largest
        first). Returns the amount actually allocated. Persists."""
        with _LOCK:
            allocated = 0
            for r in sorted([x for x in self._items if x.type == rtype],
                            key=lambda x: -x.quantity):
                if qty <= 0:
                    break
                take = min(r.quantity, qty)
                r.quantity -= take
                r.updated_at = _now()
                allocated += take
                qty -= take
            self._save()
            return allocated


STORE = ResourceStore()
