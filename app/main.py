from fastapi import FastAPI

app = FastAPI(title="AI Claim Validation")

@app.get("/health")
def health():
    return {"status": "ok"}
