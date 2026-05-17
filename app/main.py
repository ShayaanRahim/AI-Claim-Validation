from fastapi import FastAPI
from app.api import claims, validation, ai_validation, review

app = FastAPI(title="AI Claim Validation")

app.include_router(claims.router)
app.include_router(validation.router)
app.include_router(ai_validation.router)
app.include_router(review.router)

@app.get("/health")
def health():
    return {"status": "ok"}
