"""
Mini Foundry Ontology Action Runtime — FastAPI application entry point.
"""

from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Mini Foundry Ontology Action Runtime",
    description="Enterprise procurement risk review — ontology + agent + action runtime",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "mini-foundry-ontology-runtime",
    }


# ---------------------------------------------------------------------------
# Router registration (safe imports — avoids crashes when a module is WIP)
# ---------------------------------------------------------------------------
try:
    from app.api.suppliers import router as suppliers_router
    app.include_router(suppliers_router)
except ImportError:
    pass

try:
    from app.api.orders import router as orders_router
    app.include_router(orders_router)
except ImportError:
    pass

try:
    from app.api.risks import router as risks_router
    app.include_router(risks_router)
except ImportError:
    pass

try:
    from app.api.policies import router as policies_router
    app.include_router(policies_router)
except ImportError:
    pass
