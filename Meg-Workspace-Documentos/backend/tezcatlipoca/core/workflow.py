from __future__ import annotations
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

WorkflowHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]

@dataclass
class WorkflowStep:
    name: str
    handler: WorkflowHandler

@dataclass
class WorkflowRun:
    id: str
    name: str
    input: dict[str, Any]
    status: str = "queued"
    history: list[dict[str, Any]] = field(default_factory=list)

class WorkflowEngine:
    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}

    def create(self, name: str, payload: dict[str, Any]) -> WorkflowRun:
        run = WorkflowRun(id=str(uuid.uuid4()), name=name, input=payload)
        self._runs[run.id] = run
        return run

    async def execute(self, run: WorkflowRun, steps: list[WorkflowStep]) -> WorkflowRun:
        run.status = "running"
        current = dict(run.input)
        for step in steps:
            result = step.handler(current)
            if asyncio.iscoroutine(result):
                result = await result
            run.history.append({
                "step": step.name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "output": result,
            })
            if isinstance(result, dict):
                current.update(result)
        run.status = "completed"
        return run
