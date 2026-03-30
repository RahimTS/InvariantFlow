from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.ingestion.extractor import Extractor
from app.agents.ingestion.normalizer import Normalizer
from app.agents.ingestion.pipeline import IngestionPipeline
from app.agents.ingestion.rule_validator import RuleValidator
from app.llm.client import create_openrouter_client
from app.memory.rule_store import RuleStore

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


class IngestRequest(BaseModel):
    source: str
    text: str
    db_path: str | None = None


@router.post("/ingest")
async def ingest_text(body: IngestRequest) -> dict:
    store = RuleStore(db_path=body.db_path or "invariantflow.db")
    await store.init()
    llm_client = create_openrouter_client()
    pipeline = IngestionPipeline(
        rule_store=store,
        extractor=Extractor(),
        normalizer=Normalizer(llm_client=llm_client),
        validator=RuleValidator(),
    )
    return await pipeline.ingest_text(source=body.source, text=body.text)

