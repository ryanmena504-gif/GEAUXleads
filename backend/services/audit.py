"""Audit trail and idempotency for outreach decisions.

Every approve / revert / do-not-contact / message-edit passes through here so
there is an answerable record of who decided what, against which record state,
and whether the policy was satisfied at decision time.

Storage is deliberately pluggable. The default sink keeps a bounded in-memory
ring buffer and emits one structured log line per event, which survives to the
platform log even though the buffer does not survive a restart. Swapping in a
durable sink (an Airtable `Audit log` table, Postgres, S3) means implementing
`AuditSink.write` — no call site changes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

log = logging.getLogger("bloodhound.audit")

DEFAULT_BUFFER_SIZE = 500
DEFAULT_IDEMPOTENCY_SIZE = 1000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuditEvent:
    """One recorded decision.

    `eligibility` captures the policy verdict *at decision time* — the record
    can change afterwards, and an audit trail that re-derives the verdict on
    read would rewrite history.
    """

    event_id: str
    action: str
    entity_type: str
    entity_id: str
    occurred_at: str
    actor: str
    outcome: str  # accepted | rejected | error | replayed
    idempotency_key: Optional[str] = None
    reason: Optional[str] = None
    eligibility: Optional[Dict[str, Any]] = None
    changes: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditSink(Protocol):
    def write(self, event: AuditEvent) -> None: ...


class LoggingRingBufferSink:
    """Default sink: structured log line + bounded in-process history."""

    def __init__(self, capacity: int = DEFAULT_BUFFER_SIZE) -> None:
        self._capacity = capacity
        self._events: List[AuditEvent] = []
        self._lock = threading.Lock()

    def write(self, event: AuditEvent) -> None:
        log.info("audit %s", json.dumps(event.to_dict(), default=str, sort_keys=True))
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._capacity:
                del self._events[: len(self._events) - self._capacity]

    def recent(self, limit: int = 50, entity_id: Optional[str] = None,
               action: Optional[str] = None) -> List[AuditEvent]:
        with self._lock:
            events = list(self._events)
        if entity_id:
            events = [e for e in events if e.entity_id == entity_id]
        if action:
            events = [e for e in events if e.action == action]
        return list(reversed(events))[:limit]


class IdempotencyStore:
    """Bounded LRU of idempotency key -> stored response.

    Guards the window between "operator double-clicks Approve" and "a retrying
    Make webhook replays the same dispatch". Bounded and in-process today; the
    same interface backs a Redis/Airtable implementation when outreach actually
    dispatches messages (see docs/INTEGRATIONS.md).
    """

    def __init__(self, capacity: int = DEFAULT_IDEMPOTENCY_SIZE) -> None:
        self._capacity = capacity
        self._entries: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
            return entry

    def put(self, key: str, value: Dict[str, Any]) -> None:
        if not key:
            return
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)

    def invalidate(self, key: str) -> bool:
        """Drop a stored response so the same key can be used again.

        Needed when a decision is deliberately undone: without this a revert
        followed by a re-approve on the same day would be treated as a replay
        and silently return the stale response.
        """
        if not key:
            return False
        with self._lock:
            return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def derive_idempotency_key(action: str, entity_id: str,
                           scope: Optional[str] = None) -> str:
    """Deterministic key for callers that do not supply one.

    Scoped to the UTC day by default: a repeated approve of the same lead on the
    same day is a replay, while a deliberate re-approval tomorrow is a new
    decision.
    """
    scope = scope or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = hashlib.sha256(f"{action}:{entity_id}:{scope}".encode("utf-8")).hexdigest()
    return f"idem_{digest[:32]}"


class AuditLog:
    """Facade the services call. Owns the sink and the idempotency store."""

    def __init__(self, sink: Optional[AuditSink] = None,
                 idempotency: Optional[IdempotencyStore] = None) -> None:
        self.sink = sink or LoggingRingBufferSink()
        self.idempotency = idempotency or IdempotencyStore()
        self._counter = 0
        self._lock = threading.Lock()

    def _next_event_id(self) -> str:
        with self._lock:
            self._counter += 1
            counter = self._counter
        return f"evt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}_{counter:04d}"

    def record(self, action: str, entity_id: str, outcome: str,
               entity_type: str = "lead", actor: Optional[str] = None,
               reason: Optional[str] = None,
               eligibility: Optional[Dict[str, Any]] = None,
               changes: Optional[Dict[str, Any]] = None,
               idempotency_key: Optional[str] = None,
               metadata: Optional[Dict[str, Any]] = None) -> AuditEvent:
        event = AuditEvent(
            event_id=self._next_event_id(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            occurred_at=_now(),
            actor=actor or os.environ.get("BLOODHOUND_OPERATOR", "operator"),
            outcome=outcome,
            idempotency_key=idempotency_key,
            reason=reason,
            eligibility=eligibility,
            changes=changes or {},
            metadata=metadata or {},
        )
        self.sink.write(event)
        return event

    def recent(self, limit: int = 50, entity_id: Optional[str] = None,
               action: Optional[str] = None) -> List[Dict[str, Any]]:
        if not isinstance(self.sink, LoggingRingBufferSink):
            return []
        return [e.to_dict() for e in self.sink.recent(limit, entity_id, action)]


_audit_log: Optional[AuditLog] = None
_audit_lock = threading.Lock()


def get_audit_log() -> AuditLog:
    global _audit_log
    if _audit_log is None:
        with _audit_lock:
            if _audit_log is None:
                _audit_log = AuditLog()
    return _audit_log


def reset_audit_log() -> None:
    global _audit_log
    _audit_log = None
