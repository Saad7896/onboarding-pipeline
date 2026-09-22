import io

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="Onboarding Pipeline API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported for now")

    content = await file.read()
    # Read everything as text so we never silently change the customer's values
    df = pd.read_csv(io.BytesIO(content), dtype=str)

    profile = []
    for column in df.columns:
        values = df[column]
        profile.append({
            "column": column,
            "null_pct": round(values.isna().mean() * 100, 1),
            "distinct_values": int(values.nunique()),
            "samples": values.dropna().head(3).tolist(),
        })

    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": list(df.columns),
        "profile": profile,
    }