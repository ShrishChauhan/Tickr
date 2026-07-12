# Explain-this-move service — builds AI context and orchestrates the cache
from datetime import datetime, timezone

from ..analysis.interface import AnalysisEngine
from ..cache.layered import LayeredCacheBackend
from ..cache.ttl_config import EXPLAIN_TTL_SECONDS
from ..schema.explain import ExplainRequest, ExplainResult


def _cache_key(req: ExplainRequest) -> str:
    # bucket change_pct to the nearest whole point so cache reuse survives price jitter
    # but still invalidates once the move meaningfully changes
    bucket = round(req.change_pct) if req.change_pct is not None else 0
    return f"explain:{req.ticker.upper()}:{bucket}"


def _build_context(req: ExplainRequest) -> str:
    lines = [f"Asset: {req.ticker} ({req.asset_type})", f"Current price: {req.current_price}"]
    if req.change_pct is not None:
        lines.append(f"Change today: {req.change_pct:+.2f}%")
    if req.gross_margin is not None:
        lines.append(f"Gross margin: {req.gross_margin * 100:.1f}%")
    if req.pe_ratio is not None:
        lines.append(f"P/E ratio: {req.pe_ratio:.1f}x")
    lines.append("")
    lines.append("Give brief educational context for a retail investor about this move and/or these metrics.")
    return "\n".join(lines)


async def get_explanation(cache: LayeredCacheBackend, engine: AnalysisEngine, req: ExplainRequest) -> ExplainResult:
    cache_key = _cache_key(req)
    raw = await cache.get(cache_key)
    if raw is not None:
        return ExplainResult(
            ticker=req.ticker,
            explanation=raw["explanation"],
            generated_at=datetime.fromisoformat(raw["generated_at"]),
            cached=True,
        )

    explanation = await engine.explain(_build_context(req))
    generated_at = datetime.now(timezone.utc)

    await cache.set(
        cache_key,
        {"explanation": explanation, "generated_at": generated_at.isoformat()},
        EXPLAIN_TTL_SECONDS,
        data_type="explain",
        ticker=req.ticker.upper(),
    )

    return ExplainResult(ticker=req.ticker, explanation=explanation, generated_at=generated_at, cached=False)
