import io

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from pipeline.runner import get_approved_version, run_pipeline
from pipeline.loader import list_exceptions, load_results, resolve_exception
from pipeline.drift import detect_drift
from pipeline.profiler import profile_dataframe, schema_fingerprint

from pipeline.db import init_db
from pipeline.mapper import propose_mapping
from pipeline.profiler import profile_dataframe, schema_fingerprint
from pipeline.versioning import approve, list_versions, save_proposal

app = FastAPI(title="Onboarding Pipeline API")


@app.on_event("startup")
def startup():
    init_db()


class FieldOverride(BaseModel):
    canonical_field: str
    source_column: str | None = None
    transforms: list[str] | None = None
    reason: str = ""


class ApprovalRequest(BaseModel):
    approved_by: str
    overrides: list[FieldOverride] = []

class ResolveRequest(BaseModel):
    action: str              # "fix" or "waive"
    resolved_by: str
    note: str = ""
    corrected_value: str | None = None

async def read_csv_upload(file: UploadFile) -> pd.DataFrame:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported for now")
    content = await file.read()
    return pd.read_csv(io.BytesIO(content), dtype=str)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    df = await read_csv_upload(file)
    profiles = profile_dataframe(df)
    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": list(df.columns),
        "source_fingerprint": schema_fingerprint(profiles)[:12],
        "profile": profiles,
    }


@app.post("/mappings/propose")
async def propose(
    file: UploadFile = File(...),
    customer: str = Form("acme"),
    source_system: str = Form("crm"),
):
    df = await read_csv_upload(file)
    profiles = profile_dataframe(df)
    proposal = propose_mapping(profiles)
    return save_proposal(customer, source_system, proposal, schema_fingerprint(profiles))


@app.post("/mappings/{spec_id}/approve")
def approve_mapping(spec_id: int, request: ApprovalRequest):
    result = approve(
        spec_id,
        request.approved_by,
        [o.model_dump(exclude_none=True) for o in request.overrides],
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result)
    return result


@app.get("/mappings/{spec_id}/versions")
def versions(spec_id: int):
    return list_versions(spec_id)

@app.get("/exceptions")
def exceptions(status: str | None = None, batch_id: int | None = None):
    return list_exceptions(status, batch_id)


@app.post("/pipeline/{spec_id}/run")
async def run(spec_id: int, file: UploadFile = File(...)):
    version = get_approved_version(spec_id)
    if version is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "no_approved_mapping",
                    "message": "Approve a mapping for this spec before running the pipeline."},
        )
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported for now")

    raw_bytes = await file.read()
    df = pd.read_csv(io.BytesIO(raw_bytes), dtype=str)

    drift = detect_drift(profile_dataframe(df), version)
    if drift["drift_detected"] and not drift["safe_to_run"]:
        raise HTTPException(status_code=409, detail={"error": "schema_drift", **drift})

    result = run_pipeline(df, version.fields)
    load_summary = load_results(spec_id, version.version, file.filename, raw_bytes, result)

    return {
        "mapping_version": version.version,
        "drift": drift,
        "total_rows": result["total_rows"],
        "valid_count": result["valid_count"],
        "exception_count": result["exception_count"],
        "load": load_summary,
        "exceptions": result["exceptions"],
    }

@app.post("/pipeline/{spec_id}/check-drift")
async def check_drift(spec_id: int, file: UploadFile = File(...)):
    version = get_approved_version(spec_id)
    if version is None:
        raise HTTPException(status_code=422, detail={"error": "no_approved_mapping"})
    df = await read_csv_upload(file)
    return detect_drift(profile_dataframe(df), version)