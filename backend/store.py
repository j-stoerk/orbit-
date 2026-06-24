"""In-memory incident store (thread-safe). Swappable for a DB later."""
from __future__ import annotations
import threading
from typing import Dict, List, Optional

from .models import Incident


class IncidentStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._items: Dict[str, Incident] = {}
        self._sitrep_counter = 0

    def next_sitrep_number(self) -> int:
        with self._lock:
            self._sitrep_counter += 1
            return self._sitrep_counter

    def add(self, incident: Incident) -> Incident:
        with self._lock:
            self._items[incident.id] = incident
        return incident

    def get(self, incident_id: str) -> Optional[Incident]:
        return self._items.get(incident_id)

    def all(self) -> List[Incident]:
        return sorted(self._items.values(), key=lambda i: i.created_at, reverse=True)

    def update(self, incident: Incident):
        with self._lock:
            self._items[incident.id] = incident


STORE = IncidentStore()
