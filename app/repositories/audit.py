from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AuditResult, AuditTask, AuditTaskStatus


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_task(self, *, content: str, requested_platforms: list[str]) -> AuditTask:
        task = AuditTask(
            content=content,
            requested_platforms=requested_platforms,
            status=AuditTaskStatus.PROCESSING,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def update_context(self, task: AuditTask, *, cleaned_content: str, sentence_map: list[dict[str, object]]) -> None:
        task.cleaned_content = cleaned_content
        task.sentence_map = sentence_map

    def replace_results(self, task: AuditTask, results: list[AuditResult]) -> None:
        task.results.clear()
        task.results.extend(results)

    def mark_completed(self, task: AuditTask) -> None:
        task.status = AuditTaskStatus.COMPLETED
        task.completed_at = datetime.now(UTC)

    def mark_failed(self, task: AuditTask | None, message: str) -> None:
        if task is None:
            return
        task.status = AuditTaskStatus.FAILED
        task.error_message = message
        task.completed_at = datetime.now(UTC)

