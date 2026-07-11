"""Оптимизированный профиль локального RAG (qwen3:4b)."""

from __future__ import annotations

from dataclasses import dataclass

from llm import GenOptions

DEFAULT_MODEL = "qwen3:4b"


@dataclass(frozen=True)
class PipelineConfig:
    retrieve_k: int = 12
    rag_k: int = 3
    min_score: float = 0.15


@dataclass(frozen=True)
class RAGProfile:
    model: str
    gen: GenOptions
    pipeline: PipelineConfig
    simple_top_k: int
    max_chunk_chars: int

    def summary(self) -> str:
        return (
            f"model={self.model} · retrieve={self.pipeline.retrieve_k}→{self.pipeline.rag_k} · "
            f"T={self.gen.temperature} · num_ctx={self.gen.num_ctx} · "
            f"chunk≤{self.max_chunk_chars} · compact prompt"
        )


def load_profile() -> RAGProfile:
    return RAGProfile(
        model=DEFAULT_MODEL,
        gen=GenOptions(temperature=0.0, num_ctx=8192),
        pipeline=PipelineConfig(),
        simple_top_k=6,
        max_chunk_chars=1200,
    )
