from __future__ import annotations

from app.schemas.audit import AuditReport, AuditResponse, PlatformAuditReport
from app.schemas.common import AuditTaskSummary, CandidateTagHit, SentenceSegment


class ReportService:
    def build_platform_report(
        self,
        *,
        platform_report: PlatformAuditReport,
    ) -> dict[str, object]:
        return platform_report.model_dump(mode="json")

    def build_response(
        self,
        *,
        task: AuditTaskSummary,
        original_content: str,
        cleaned_content: str,
        sentence_segments: list[SentenceSegment],
        platform_results: list[PlatformAuditReport],
    ) -> AuditResponse:
        return AuditResponse(
            report=AuditReport(
                task=task,
                original_content=original_content,
                cleaned_content=cleaned_content,
                sentence_segments=sentence_segments,
                platform_results=platform_results,
            )
        )

    def filter_candidate_tags(
        self,
        candidate_hits: list[CandidateTagHit],
        sentence_ids: set[int],
    ) -> list[CandidateTagHit]:
        return [hit for hit in candidate_hits if hit.sentence_id in sentence_ids]

