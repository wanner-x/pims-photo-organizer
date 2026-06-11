from fastapi import FastAPI

app = FastAPI(title="PIMS V1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
