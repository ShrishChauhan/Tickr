# Stub routers for Phase 1 endpoints — TODO(Phase 1): implement each route
# TODO(Phase 1): GET /companies/{ticker} — resolve company identity
# TODO(Phase 1): GET /companies/{ticker}/fundamentals — normalized financials
# TODO(Phase 1): GET /companies/{ticker}/filings — filing references
# TODO(Phase 2): POST /companies/{ticker}/analyze — AI analysis Q&A
from fastapi import APIRouter

router = APIRouter()
