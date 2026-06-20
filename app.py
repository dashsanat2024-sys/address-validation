"""Flask API for UK address validation and normalization."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, Response

# Allow `python app.py` from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from address_validation.batch_processor import iter_batch_events, iter_batch_results  # noqa: E402
from address_validation.export import client_csv_string, db_csv_string  # noqa: E402
from address_validation.pipeline import AddressPipeline  # noqa: E402
from address_validation.review_store import record_correction  # noqa: E402
from address_validation.schema import CLIENT_FIELD_LABELS  # noqa: E402
from address_validation.vendor_import import (  # noqa: E402
    DEFAULT_MAPPING_PATH,
    load_mapping_config,
    parse_csv_rows,
)

from address_validation.ollama_client import ping_ollama, warm_model  # noqa: E402
from address_validation.azure_cost import arthavi_comparison_baseline  # noqa: E402
from address_validation.azure_normalize import (  # noqa: E402
    azure_configured,
    azure_deployment_name,
    cloud_llm_provider_label,
    run_azure_normalize,
)
from address_validation.local_address_store import (  # noqa: E402
    index_path,
    is_local_index_available,
    record_count,
)

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"
pipeline = AddressPipeline()
app = Flask(__name__, static_folder=str(STATIC_DIR))


@app.get("/")
def review_ui():
    return send_from_directory(STATIC_DIR, "index.html")


def _ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _ollama_enabled_by_default() -> bool:
    return os.getenv("CLOUD_DEFAULT_SKIP_LLM", "0") != "1"


def _default_skip_validation() -> bool:
    return os.getenv("ADDRESS_SKIP_VALIDATION", "0") == "1"


@app.get("/health")
def health():
    validator = os.getenv("ADDRESS_VALIDATOR", "postcodes_io")
    ollama_enabled = _ollama_enabled_by_default()
    skip_validation = _default_skip_validation()
    ollama_ok, ollama_msg = ping_ollama()
    return jsonify(
        {
            "status": "ok",
            "model": pipeline.model,
            "validator": validator if not skip_validation else "llm_only",
            "ideal_postcodes_configured": bool(os.getenv("IDEAL_POSTCODES_API_KEY")),
            "ollama_host": _ollama_host(),
            "ollama_enabled": ollama_enabled,
            "ollama_reachable": ollama_ok,
            "ollama_status": ollama_msg,
            "llm_default_skipped": not ollama_enabled,
            "skip_validation_default": skip_validation,
            "azure_configured": azure_configured(),
            "azure_deployment": azure_deployment_name() if azure_configured() else None,
            "cloud_llm_provider": cloud_llm_provider_label() if azure_configured() else None,
            "rag_enabled_default": os.getenv("RAG_ENABLED", "1").strip().lower() in {"1", "true", "yes"},
            "local_address_index": str(index_path()),
            "local_address_index_loaded": is_local_index_available(),
            "local_address_records": record_count() if is_local_index_available() else 0,
        }
    )


@app.get("/api/config")
def server_config():
    validator = os.getenv("ADDRESS_VALIDATOR", "postcodes_io")
    skip_validation = _default_skip_validation()
    labels = {
        "postcodes_io": "Postcodes.io (free — postcode area validation)",
        "ideal_postcodes": "Ideal Postcodes (street-level, needs API key)",
        "llm_only": "Ollama only (external validation bypassed)",
    }
    active = "llm_only" if skip_validation else validator
    return jsonify(
        {
            "model": pipeline.model,
            "validator": active,
            "validator_label": labels.get(active, active),
            "ideal_postcodes_configured": bool(os.getenv("IDEAL_POSTCODES_API_KEY")),
            "ollama_host": _ollama_host(),
            "ollama_enabled": _ollama_enabled_by_default(),
            "skip_validation_default": skip_validation,
            "azure_configured": azure_configured(),
            "azure_deployment": azure_deployment_name() if azure_configured() else None,
            "cloud_llm_provider": cloud_llm_provider_label() if azure_configured() else None,
            "rag_enabled_default": os.getenv("RAG_ENABLED", "1").strip().lower() in {"1", "true", "yes"},
        }
    )


def _parse_bool(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes"}


def _parse_batch_options(form: dict) -> tuple[bool, bool, str | None]:
    if "skip_llm" in form:
        skip_llm = _parse_bool(form.get("skip_llm"))
    else:
        skip_llm = os.getenv("CLOUD_DEFAULT_SKIP_LLM", "0") == "1"

    if "skip_validation" in form:
        skip_validation = _parse_bool(form.get("skip_validation"))
    else:
        skip_validation = _default_skip_validation()

    validator = (form.get("validator") or "").strip() or None
    return skip_llm, skip_validation, validator


def _read_uploaded_csv(uploaded) -> io.TextIOWrapper:
    raw = uploaded.read()
    return io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig")


def _make_pipeline(body: dict) -> AddressPipeline:
    skip_llm = bool(body.get("skip_llm", False))
    if not skip_llm and os.getenv("CLOUD_DEFAULT_SKIP_LLM", "0") == "1":
        skip_llm = True
    skip_validation = bool(body.get("skip_validation", False))
    if not skip_validation and _default_skip_validation():
        skip_validation = True
    validator = (body.get("validator") or "").strip() or None
    model = (body.get("model") or "").strip() or None
    return AddressPipeline(
        model=model,
        skip_llm=skip_llm,
        skip_validation=skip_validation,
        validator=validator,
        ollama_host=os.getenv("OLLAMA_HOST"),
    )


@app.post("/api/normalize")
def normalize_address():
    import time

    body = request.get_json(silent=True) or {}
    address = (body.get("address") or "").strip()
    if not address:
        return jsonify({"error": "address is required"}), 400

    customer_id = (body.get("customer_id") or "").strip()
    llm_provider = (body.get("llm_provider") or "arthavi").strip().lower()
    use_rag = body.get("use_rag")
    if use_rag is None:
        use_rag = os.getenv("RAG_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    else:
        use_rag = bool(use_rag)

    if llm_provider == "azure":
        if not azure_configured():
            return jsonify({"error": "Azure OpenAI is not configured on the server"}), 503
        skip_validation = bool(body.get("skip_validation", False))
        if not skip_validation and _default_skip_validation():
            skip_validation = True
        try:
            result, llm_analysis = run_azure_normalize(
                address,
                customer_id=customer_id,
                skip_validation=skip_validation,
                use_rag=use_rag,
            )
        except Exception as exc:
            return jsonify({"error": str(exc), "llm_provider": "azure"}), 502
        payload = result.to_dict()
        payload["llm_provider"] = "azure"
        payload["llm_analysis"] = llm_analysis
        payload["rag_metadata"] = result.rag_metadata
        status = 200 if result.success else 422
        return jsonify(payload), status

    runner = _make_pipeline(body)
    started = time.perf_counter()
    result = runner.run(address, customer_id=customer_id, use_rag=use_rag)
    latency_ms = (time.perf_counter() - started) * 1000
    payload = result.to_dict()
    payload["llm_provider"] = "arthavi"
    payload["rag_metadata"] = result.rag_metadata
    if not body.get("skip_llm", False):
        arthavi = arthavi_comparison_baseline()
        payload["llm_analysis"] = {
            "provider": "arthavi",
            "model": result.model,
            "latency_ms": round(latency_ms, 1),
            "token_usage": None,
            "cost_analysis": {
                "cost_usd": {"total_per_request": 0.0},
                "projections_usd": {
                    "per_1_000_addresses": 0.0,
                    "per_10_000_addresses": 0.0,
                    "per_100_000_addresses": 0.0,
                    "per_1_000_000_addresses": 0.0,
                },
            },
            "comparison": {
                "arthavi": {
                    **arthavi,
                    "latency_ms": round(latency_ms, 1),
                },
                "azure": {
                    "provider": "azure",
                    "model": azure_deployment_name() or "Azure deployment",
                    "cost_usd_per_request": "varies — run Azure to measure",
                    "tokens_per_request": "varies",
                    "typical_latency_seconds": "5–20",
                    "data_residency": "Azure cloud",
                },
            },
            "rag_metadata": result.rag_metadata,
        }
    status = 200 if result.success else 422
    return jsonify(payload), status


@app.post("/api/validate-postcode")
def validate_postcode_only():
    body = request.get_json(silent=True) or {}
    postcode = (body.get("postcode") or "").strip()
    if not postcode:
        return jsonify({"error": "postcode is required"}), 400

    runner = _make_pipeline(body)
    validation = runner.validator.validate_postcode(postcode)
    return jsonify(
        {
            "valid": validation.valid,
            "postcode": validation.postcode,
            "admin_district": validation.admin_district,
            "region": validation.region,
            "country": validation.country,
            "street_level_validated": validation.street_level_validated,
            "confidence": validation.confidence,
            "source": validation.source,
            "error": validation.error,
        }
    ), (200 if validation.valid else 422)


@app.post("/api/import/preview")
def import_preview():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "CSV file required (form field: file)"}), 400

    config = load_mapping_config()
    override = config.get("override") or {}
    preview = parse_csv_rows(io.TextIOWrapper(uploaded.stream, encoding="utf-8-sig"), override, limit=5)
    return jsonify(
        {
            "format_detected": preview.format_detected,
            "column_mapping": preview.column_mapping,
            "header_row": preview.header_row,
            "total_rows": preview.total_rows,
            "sample_rows": [
                {
                    "customer_id": r.customer_id,
                    "vendor_address": r.vendor_address,
                    "source_columns": r.source_columns,
                }
                for r in preview.sample_rows
            ],
        }
    )


@app.post("/api/import/queue")
def import_queue():
    """Parse CSV and return rows for UI queue (does not run LLM)."""
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "CSV file required (form field: file)"}), 400

    config = load_mapping_config()
    override = config.get("override") or {}
    preview = parse_csv_rows(io.TextIOWrapper(uploaded.stream, encoding="utf-8-sig"), override)
    return jsonify(
        {
            "format_detected": preview.format_detected,
            "column_mapping": preview.column_mapping,
            "header_row": preview.header_row,
            "total_rows": preview.total_rows,
            "rows": [
                {"customer_id": r.customer_id, "vendor_address": r.vendor_address}
                for r in preview.sample_rows
            ],
        }
    )


@app.post("/api/import/batch")
def import_batch():
    """Parse CSV and normalize every row (can be slow with LLM)."""
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "CSV file required (form field: file)"}), 400

    body = request.form.to_dict()
    skip_llm, skip_validation, validator = _parse_batch_options(body)
    runner = AddressPipeline(
        skip_llm=skip_llm,
        skip_validation=skip_validation,
        validator=validator,
    )

    config = load_mapping_config()
    override = config.get("override") or {}
    preview = parse_csv_rows(io.TextIOWrapper(uploaded.stream, encoding="utf-8-sig"), override)

    results = []
    ok = 0
    for row in preview.sample_rows:
        result = runner.run(row.vendor_address, customer_id=row.customer_id)
        results.append(result.to_dict())
        if result.success:
            ok += 1

    return jsonify(
        {
            "format_detected": preview.format_detected,
            "total_rows": preview.total_rows,
            "processed": len(results),
            "successful": ok,
            "results": results,
        }
    )


@app.post("/api/import/batch/process")
def import_batch_process():
    """Process each CSV row one-by-one; stream NDJSON progress; final line includes DB CSV."""
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "CSV file required (form field: file)"}), 400

    body = request.form.to_dict()
    skip_llm, skip_validation, validator = _parse_batch_options(body)
    file_stream = _read_uploaded_csv(uploaded)

    def generate():
        results: list[dict] = []
        try:
            for event in iter_batch_events(
                file_stream,
                skip_llm=skip_llm,
                skip_validation=skip_validation,
                validator=validator,
            ):
                evt_type = event.get("type")
                if evt_type == "progress":
                    results.append(event)
                yield json.dumps(event) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"
            return

        stats = {
            "total": len(results),
            "successful": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
        }
        yield json.dumps(
            {
                "type": "complete",
                "stats": stats,
                "csv": db_csv_string(results),
                "filename": "db_client_addresses.csv",
            }
        ) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@app.post("/api/export/db-csv")
def export_db_csv():
    body = request.get_json(silent=True) or {}
    results = body.get("results")
    if not isinstance(results, list):
        return jsonify({"error": "results array required"}), 400
    return Response(
        db_csv_string(results),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=db_client_addresses.csv"},
    )


@app.post("/api/export/client-csv")
def export_client_csv_only():
    body = request.get_json(silent=True) or {}
    results = body.get("results")
    if not isinstance(results, list):
        return jsonify({"error": "results array required"}), 400
    return Response(
        client_csv_string(results),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=client_addresses.csv"},
    )


@app.post("/api/import/batch/export")
def import_batch_export():
    """Batch normalize vendor CSV and download DB-ready CSV (legacy fast path)."""
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "CSV file required (form field: file)"}), 400

    body = request.form.to_dict()
    skip_llm, skip_validation, validator = _parse_batch_options(body)
    file_stream = _read_uploaded_csv(uploaded)

    results = list(
        iter_batch_results(
            file_stream,
            skip_llm=skip_llm,
            skip_validation=skip_validation,
            validator=validator,
        )
    )
    csv_data = db_csv_string(results)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=db_client_addresses.csv"},
    )


@app.get("/api/schema")
def client_schema():
    schema_path = Path(__file__).resolve().parent / "config" / "schema.json"
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    payload["field_labels"] = CLIENT_FIELD_LABELS
    return jsonify(payload)


@app.post("/api/review")
def submit_human_correction():
    body = request.get_json(silent=True) or {}
    vendor_address = (body.get("vendor_address") or "").strip()
    human_corrected = body.get("human_corrected")
    if not vendor_address or not isinstance(human_corrected, dict):
        return jsonify({"error": "vendor_address and human_corrected are required"}), 400

    record_correction(
        vendor_address=vendor_address,
        llm_output=body.get("llm_output") or {},
        human_corrected=human_corrected,
        customer_id=(body.get("customer_id") or "").strip(),
    )
    return jsonify({"status": "saved"})


@app.get("/api/config/vendor-mapping")
def vendor_mapping_config():
    if not DEFAULT_MAPPING_PATH.exists():
        return jsonify({"override": {}})
    return jsonify(json.loads(DEFAULT_MAPPING_PATH.read_text(encoding="utf-8")))


if __name__ == "__main__":
    if os.getenv("OLLAMA_WARMUP", "1") == "1" and _ollama_enabled_by_default():
        import threading

        def _bg_warm() -> None:
            warm_model(os.getenv("OLLAMA_MODEL", pipeline.model))

        threading.Thread(target=_bg_warm, daemon=True).start()
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5050")))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
