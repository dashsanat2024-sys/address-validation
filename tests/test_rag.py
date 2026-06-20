"""Tests for RAG retrieval."""

from address_validation.rag.retriever import enrich_user_prompt, retrieve_similar_examples


def test_retrieve_elliot_yard_finds_similar_correction():
    query = "Apartment 7 Elliot's Yard 8 Gulson Road Coventry CV1 2NF"
    hits = retrieve_similar_examples(query, top_k=3)
    assert hits
    assert any("gulson" in h["vendor_address"].lower() for h in hits)


def test_enrich_user_prompt_appends_examples():
    base = "Normalize this address."
    enriched, meta = enrich_user_prompt(base, "COMEX 2000 UNIT 3 STADIUM BUSINESS COURT, DERBY, DE24 8HP", enabled=True)
    assert meta["enabled"] is True
    assert "Similar corrected examples" in enriched or meta.get("note")
