"""Curated evidence retrieval over the local evidence_documents table."""
from __future__ import annotations

from training.adapters.sqlite_repositories import SQLiteTrainingRepository
from training.domain.models import EvidenceDocument
from training.evidence.seeds import CURATED_EVIDENCE


class CuratedEvidenceRetriever:
    def __init__(self, repository: SQLiteTrainingRepository | None = None):
        self.repository = repository or SQLiteTrainingRepository()

    def ensure_seeded(self):
        self.repository.seed_evidence_documents(CURATED_EVIDENCE)

    def search(self, query: str, limit: int = 5) -> list[EvidenceDocument]:
        self.ensure_seeded()
        results = self.repository.search_evidence(query=query, limit=limit)
        if results:
            return results
        return self.repository.search_evidence(query="", limit=limit)
