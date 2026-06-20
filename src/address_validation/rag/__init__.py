"""RAG retrieval for UK address normalization (shared by Arthavi + Azure)."""

from .retriever import attach_local_lookup, enrich_user_prompt, is_rag_enabled, retrieve_similar_examples

__all__ = ["attach_local_lookup", "enrich_user_prompt", "is_rag_enabled", "retrieve_similar_examples"]
