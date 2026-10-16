"""Health route registration."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

router = APIRouter()


@router.get("/health", tags=["health"])
def health(request: Request) -> dict[str, str]:
    factory = request.app.state.session_factory
    try:
        with factory() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "database": "ready", "execution": "no-order-path"}
