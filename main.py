import io

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile

from pipeline.mapper import propose_mapping
from pipeline.profiler import profile_dataframe

app = FastAPI(title="Onboarding Pipeline API")


async def read_csv_upload(file: UploadFile) -> pd.DataFrame:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported for now")
    content = await file.read()
    # Read everything as text so we never silently change the customer's values
    return pd.read_csv(io.BytesIO(content), dtype=str)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    df = await read_csv_upload(file)
    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": list(df.columns),
        "profile": profile_dataframe(df),
    }


@app.post("/mappings/propose")
async def propose(file: UploadFile = File(...)):
    df = await read_csv_upload(file)
    return propose_mapping(profile_dataframe(df))