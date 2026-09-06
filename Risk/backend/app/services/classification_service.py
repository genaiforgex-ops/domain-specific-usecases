import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.core.config import get_settings
from app.models.agent import ClassificationAgent, ClassificationAgentRun
from app.models.classification import ClassificationJob, RegulationDocument, RegulatorClause
from app.services.ai_gateway import AIGateway
from app.services.clause_retrieval import select_relevant_clauses

LABEL_DISPLAY = {
    "financial_outsourcing": "Financial Outsourcing",
    "it_outsourcing": "IT Outsourcing",
    "non_outsourcing": "Non-Outsourcing",
}


class ClassificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai = AIGateway(db)
        self.audit = AuditService(db)
        self.settings = get_settings()

    async def get_active_clause_version(self) -> str:
        result = await self.db.execute(
            select(RegulatorClause.version).order_by(RegulatorClause.effective_from.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        return row or "v1"

    async def get_clauses_for_version(self, version: str) -> list[dict]:
        result = await self.db.execute(
            select(RegulatorClause).where(RegulatorClause.version == version)
        )
        return self._serialize_clauses(result.scalars().all())

    async def get_active_document_ids(self) -> list[str]:
        result = await self.db.execute(
            select(RegulationDocument.id).where(RegulationDocument.status == "active")
        )
        return [str(row) for row in result.scalars().all()]

    async def get_clauses_for_documents(self, document_ids: list[str]) -> list[dict]:
        result = await self.db.execute(
            select(RegulatorClause).where(RegulatorClause.document_id.in_(document_ids))
        )
        return self._serialize_clauses(result.scalars().all())

    @staticmethod
    def _serialize_clauses(clauses) -> list[dict]:
        return [
            {
                "id": c.id,
                "clause_ref": c.clause_ref,
                "text": c.text,
                "tags": c.tags,
                "regulator": c.regulator,
                "instrument": c.instrument,
                "source_doc": c.source_doc,
                "page_no": c.page_no,
                "para_no": c.para_no,
            }
            for c in clauses
        ]

    def _enrich_evidence(self, evidence: list[dict], clauses_by_id: dict[str, dict]) -> list[dict]:
        """Attach the source-document locator (doc title, page, paragraph)
        from the clause actually matched, so the UI can cite/highlight the
        exact line in the regulation — not just a clause_ref string. Done
        here rather than in the LLM prompt: the source text is static per
        clause row, no need to ask the model to re-derive it."""
        enriched = []
        for item in evidence:
            clause = clauses_by_id.get(item.get("clause_id"))
            enriched.append(
                {
                    **item,
                    "instrument": clause.get("instrument") if clause else None,
                    "source_doc": clause.get("source_doc") if clause else None,
                    "page_no": clause.get("page_no") if clause else None,
                    "para_no": clause.get("para_no") if clause else None,
                    "clause_text": clause.get("text") if clause else None,
                }
            )
        return enriched

    async def create_job(
        self,
        vendor_id: uuid.UUID,
        text: str,
        document_id: uuid.UUID | None,
        created_by: uuid.UUID,
        agent_ids: list[str] | None = None,
    ) -> ClassificationJob:
        version = await self.get_active_clause_version()
        active_document_ids = await self.get_active_document_ids()
        job = ClassificationJob(
            vendor_id=vendor_id,
            document_id=document_id,
            input_text=text,
            status="pending",
            clause_library_version=version,
            clause_document_ids=active_document_ids,
            agent_ids=agent_ids or None,
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def run_classification(self, job_id: uuid.UUID, actor_id: uuid.UUID | None) -> ClassificationJob:
        """Run the job, and make sure a failure is recorded rather than hung.

        Without the except below, an LLM or clause-lookup error propagates out of
        the background task with the session uncommitted, so the row keeps
        whatever status it had at creation and every poller waits forever. Mark
        it failed on its own transaction, then re-raise for the logs.
        """
        try:
            return await self._run_classification(job_id, actor_id)
        except Exception as exc:
            await self.db.rollback()
            result = await self.db.execute(
                select(ClassificationJob).where(ClassificationJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job is not None:
                job.status = "failed"
                job.justification = f"Classification failed: {exc}"[:2000]
                await self.db.commit()
            raise

    async def _run_classification(self, job_id: uuid.UUID, actor_id: uuid.UUID | None) -> ClassificationJob:
        result = await self.db.execute(
            select(ClassificationJob).where(ClassificationJob.id == job_id)
        )
        job = result.scalar_one()
        job.status = "processing"
        # Committed, not just flushed: this method only ever runs inside
        # run_classification_bg's own session, and until it lands the row still
        # reads as "pending" to everyone polling for progress.
        await self.db.commit()

        text = job.input_text or ""
        # Jobs created after the Library feature pin the exact set of active
        # documents at creation time (clause_document_ids); jobs created
        # before it only have clause_library_version — that legacy path is
        # left untouched so old results stay reproducible.
        #
        # Must check "is not None", not truthiness: an empty list means this
        # job was created when zero documents were active — that's a real
        # "no clauses available" state, not a signal to fall back to the
        # legacy version lookup (which ignores archive status entirely and
        # would incorrectly resurrect archived documents' clauses).
        if job.clause_document_ids is not None:
            clauses = await self.get_clauses_for_documents(job.clause_document_ids)
        else:
            clauses = await self.get_clauses_for_version(job.clause_library_version or "v1")

        rbi_clauses_all = [c for c in clauses if c["regulator"] == "RBI"]
        sebi_clauses_all = [c for c in clauses if c["regulator"] == "SEBI"]

        # Narrow to the top-K most relevant clauses before they go into the
        # prompt — a no-op while a corpus is small (today's hand-curated
        # rows), but keeps a fully-ingested 90+ page SEBI circular from
        # being dumped into every single classify call. See clause_retrieval.
        top_k = self.settings.m1_retrieval_top_k
        rbi_clauses = select_relevant_clauses(text, rbi_clauses_all, top_k)
        sebi_clauses = select_relevant_clauses(text, sebi_clauses_all, top_k)
        rbi_by_id = {str(c["id"]): c for c in rbi_clauses}
        sebi_by_id = {str(c["id"]): c for c in sebi_clauses}

        # Agents selected → run each and record a ClassificationAgentRun so the
        # Review screen can lay results out side-by-side; the first selected agent
        # is also mirrored onto the job (ai_/rbi_/sebi_ fields) so History,
        # reporting, and confirm/override keep working unchanged. No agents → the
        # built-in default run writes straight onto the job, exactly as before.
        agents = await self._load_agents(job.agent_ids)
        if agents:
            for i, agent in enumerate(agents):
                rbi_result, sebi_result = await self._classify_pair(
                    text, rbi_clauses, sebi_clauses, job.id, actor_id,
                    rbi_prompt=agent.rbi_prompt, sebi_prompt=agent.sebi_prompt,
                    model_version=agent.model_version, temperature=agent.temperature,
                    agent_name=agent.name,
                )
                run = ClassificationAgentRun(
                    job_id=job.id,
                    agent_id=agent.id,
                    agent_name=agent.name,
                    status="ready",
                    agent_snapshot={
                        "rbi_prompt": agent.rbi_prompt,
                        "sebi_prompt": agent.sebi_prompt,
                        "model_version": agent.model_version,
                        "temperature": agent.temperature,
                    },
                )
                self._apply_results(run, rbi_result, sebi_result, rbi_by_id, sebi_by_id)
                self.db.add(run)
                if i == 0:
                    self._apply_results(job, rbi_result, sebi_result, rbi_by_id, sebi_by_id, set_primary=True)
        else:
            rbi_result, sebi_result = await self._classify_pair(
                text, rbi_clauses, sebi_clauses, job.id, actor_id
            )
            self._apply_results(job, rbi_result, sebi_result, rbi_by_id, sebi_by_id, set_primary=True)

        job.status = "ready"

        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def _load_agents(self, agent_ids: list[str] | None) -> list[ClassificationAgent]:
        """Resolve the selected agents, preserving the user's selection order.
        Archived/deleted ids silently drop out — if that leaves none, the caller
        falls back to the built-in run so a job is never left empty."""
        if not agent_ids:
            return []
        result = await self.db.execute(
            select(ClassificationAgent).where(ClassificationAgent.id.in_(agent_ids))
        )
        by_id = {str(a.id): a for a in result.scalars().all()}
        return [by_id[a] for a in agent_ids if a in by_id]

    async def _classify_pair(
        self, text, rbi_clauses, sebi_clauses, job_id, actor_id,
        *, rbi_prompt=None, sebi_prompt=None, model_version=None, temperature=None,
        agent_name="Default",
    ):
        """Run the RBI and SEBI classify calls for one prompt set. Sequential on
        purpose: the two share this service's single AsyncSession (via the
        gateway's audit writes), which is not safe to write to concurrently.

        agent_name is recorded on the token-usage log so the Metrics panel can
        break spend down per classification agent ("Default" = built-in run)."""
        rbi_result = await self.ai.classify(
            text=text, clauses=rbi_clauses, module="M1", regulator="RBI",
            entity_id=str(job_id), actor_id=actor_id,
            system_prompt=rbi_prompt, model_version=model_version, temperature=temperature,
            agent_name=agent_name,
        )
        sebi_result = await self.ai.classify(
            text=text, clauses=sebi_clauses, module="M1", regulator="SEBI",
            entity_id=str(job_id), actor_id=actor_id,
            system_prompt=sebi_prompt, model_version=model_version, temperature=temperature,
            agent_name=agent_name,
        )
        return rbi_result, sebi_result

    def _evidence_payload(self, result, by_id: dict) -> dict:
        return {
            "evidence": self._enrich_evidence(result.evidence, by_id),
            "clause_ids": result.clause_ids,
            "reasoning": result.reasoning,
            "truncated": result.truncated,
        }

    def _apply_results(self, target, rbi_result, sebi_result, rbi_by_id, sebi_by_id, *, set_primary=False):
        """Write RBI/SEBI results onto a job or an agent-run row (both share the
        rbi_*/sebi_* field names). set_primary also fills the job's legacy
        ai_*/requires_secondary_review fields from the RBI result (SEBI fallback)."""
        if rbi_result:
            target.rbi_label = rbi_result.label
            target.rbi_confidence = rbi_result.confidence
            target.rbi_evidence = self._evidence_payload(rbi_result, rbi_by_id)
        if sebi_result:
            target.sebi_label = sebi_result.label
            target.sebi_confidence = sebi_result.confidence
            target.sebi_evidence = self._evidence_payload(sebi_result, sebi_by_id)
        if set_primary:
            primary = rbi_result or sebi_result
            if primary:
                primary_by_id = rbi_by_id if primary is rbi_result else sebi_by_id
                target.ai_label = primary.label
                target.ai_confidence = primary.confidence
                target.ai_evidence = self._evidence_payload(primary, primary_by_id)
                threshold = self.settings.m1_confidence_threshold
                min_confidence = min(r.confidence for r in [rbi_result, sebi_result] if r)
                target.requires_secondary_review = min_confidence < threshold

    async def confirm(
        self, job_id: uuid.UUID, reviewer_id: uuid.UUID, label: str | None = None, source: str | None = None
    ) -> ClassificationJob:
        result = await self.db.execute(
            select(ClassificationJob).where(ClassificationJob.id == job_id)
        )
        job = result.scalar_one()
        before = {"final_label": job.final_label}
        if label:
            job.final_label = label
        elif source == "rbi":
            job.final_label = job.rbi_label
        elif source == "sebi":
            job.final_label = job.sebi_label
        else:
            job.final_label = job.ai_label
        job.reviewer_id = reviewer_id
        job.status = "confirmed"
        await self.audit.log(
            "classification.confirmed",
            "classification_job",
            str(job.id),
            actor_id=reviewer_id,
            before=before,
            after={"final_label": job.final_label},
        )
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def override(
        self, job_id: uuid.UUID, reviewer_id: uuid.UUID, label: str, justification: str
    ) -> ClassificationJob:
        if len(justification.strip()) < 20:
            raise ValueError("Justification must be at least 20 characters")
        result = await self.db.execute(
            select(ClassificationJob).where(ClassificationJob.id == job_id)
        )
        job = result.scalar_one()
        before = {"final_label": job.final_label, "ai_label": job.ai_label}
        job.final_label = label
        job.reviewer_id = reviewer_id
        job.justification = justification
        job.status = "confirmed"
        await self.audit.log(
            "classification.override",
            "classification_job",
            str(job.id),
            actor_id=reviewer_id,
            before=before,
            after={"final_label": label, "justification": justification},
        )
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def get_vendor_classification(self, vendor_id: uuid.UUID) -> ClassificationJob | None:
        result = await self.db.execute(
            select(ClassificationJob)
            .where(ClassificationJob.vendor_id == vendor_id, ClassificationJob.status == "confirmed")
            .order_by(ClassificationJob.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
