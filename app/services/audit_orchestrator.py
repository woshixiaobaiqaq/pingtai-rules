from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AuditResult, AuditTaskStatus, Platform
from app.repositories.audit import AuditRepository
from app.schemas.audit import AuditResponse, PlatformAuditReport
from app.schemas.common import AuditTaskSummary
from app.services.candidate_screening import CandidateScreeningService
from app.services.embeddings import HashEmbeddingService
from app.services.llm_judge import RuleBoundJudgeService
from app.services.report import ReportService
from app.services.rewrite import RewriteService
from app.services.rule_recall import RuleRecallService
from app.services.text_processing import TextProcessor


class AuditOrchestratorService:
    def __init__(self, session: Session | None, rule_repository) -> None:
        self.session = session
        self.settings = get_settings()
        self.audit_repository = AuditRepository(session) if session is not None else None
        self.rule_repository = rule_repository
        self.text_processor = TextProcessor()
        self.embedding_service = HashEmbeddingService()
        self.candidate_screening_service = CandidateScreeningService()
        self.rule_recall_service = RuleRecallService(self.rule_repository, self.embedding_service)
        self.judge_service = RuleBoundJudgeService()
        self.rewrite_service = RewriteService()
        self.report_service = ReportService()

    def audit(
        self,
        *,
        content: str,
        platforms: list[Platform] | None,
        persist: bool,
    ) -> AuditResponse:
        task = None
        if self.audit_repository is None:
            persist = False
        target_platforms = platforms or [Platform(value) for value in self.settings.default_target_platform_list]
        try:
            if persist and self.audit_repository is not None:
                task = self.audit_repository.create_task(
                    content=content,
                    requested_platforms=[platform.value for platform in target_platforms],
                )

            cleaned_content = self.text_processor.clean_text(content)
            sentence_segments = self.text_processor.split_sentences(content)
            candidate_hits = self.candidate_screening_service.screen(sentence_segments)
            if persist and task is not None and self.audit_repository is not None:
                self.audit_repository.update_context(
                    task,
                    cleaned_content=cleaned_content,
                    sentence_map=[segment.model_dump(mode="json") for segment in sentence_segments],
                )

            platform_results: list[PlatformAuditReport] = []
            audit_rows: list[AuditResult] = []
            for platform in target_platforms:
                recalled_rules = self.rule_recall_service.recall(
                    platform=platform,
                    content=cleaned_content,
                    candidate_hits=candidate_hits,
                )
                risk_level, hit_sentences, matched_rules = self.judge_service.judge(
                    platform=platform,
                    sentences=sentence_segments,
                    candidate_hits=candidate_hits,
                    recalled_rules=recalled_rules,
                )
                rewrite_options, revised_text = self.rewrite_service.rewrite(
                    platform=platform,
                    original_content=content,
                    sentences=sentence_segments,
                    hit_sentences=hit_sentences,
                    risk_level=risk_level,
                )
                relevant_tags = self.report_service.filter_candidate_tags(
                    candidate_hits,
                    {hit.sentence_id for hit in hit_sentences},
                )
                platform_report = PlatformAuditReport(
                    platform=platform,
                    risk_level=risk_level,
                    candidate_tags=relevant_tags,
                    hit_sentences=hit_sentences,
                    matched_rules=matched_rules,
                    rewrite_options=rewrite_options,
                    revised_text=revised_text,
                )
                platform_results.append(platform_report)

                if persist and task is not None and self.audit_repository is not None:
                    audit_rows.append(
                        AuditResult(
                            audit_task_id=task.id,
                            platform=platform,
                            risk_level=risk_level,
                            hit_sentences=[item.model_dump(mode="json") for item in hit_sentences],
                            matched_rules=[item.model_dump(mode="json") for item in matched_rules],
                            rewrite_options=rewrite_options.model_dump(mode="json"),
                            revised_text=revised_text,
                            report=self.report_service.build_platform_report(platform_report=platform_report),
                        )
                    )

            if persist and task is not None and self.audit_repository is not None and self.session is not None:
                self.audit_repository.replace_results(task, audit_rows)
                self.audit_repository.mark_completed(task)
                self.session.commit()
                self.session.refresh(task)

            task_summary = AuditTaskSummary(
                id=task.id if task is not None else self._build_ephemeral_id(content),
                status=AuditTaskStatus.COMPLETED,
                created_at=task.created_at if task is not None else None,
                completed_at=task.completed_at if task is not None else None,
            )
            return self.report_service.build_response(
                task=task_summary,
                original_content=content,
                cleaned_content=cleaned_content,
                sentence_segments=sentence_segments,
                platform_results=platform_results,
            )
        except Exception as exc:
            if persist and task is not None and self.audit_repository is not None and self.session is not None:
                self.audit_repository.mark_failed(task, str(exc))
                self.session.commit()
            raise

    def _build_ephemeral_id(self, content: str):
        import uuid

        return uuid.uuid5(uuid.NAMESPACE_URL, content)
