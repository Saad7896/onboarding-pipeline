import io

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from pipeline.runner import get_approved_version, run_pipeline

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
@app.post("/pipeline/{spec_id}/run")
async def run(spec_id: int, file: UploadFile = File(...)):
    version = get_approved_version(spec_id)
    if version is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "no_approved_mapping",
                    "message": "Approve a mapping for this spec before running the pipeline."},
        )
    df = await read_csv_upload(file)
    result = run_pipeline(df, version.fields)
    result["mapping_version"] = version.version
    return result