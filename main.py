from fastapi import FastAPI

app = FastAPI(title="Onboarding Pipeline API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"Hello {name}, welcome to the onboarding pipeline"}