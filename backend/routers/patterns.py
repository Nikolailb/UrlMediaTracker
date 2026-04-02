from fastapi import APIRouter, HTTPException, status

from schemas.pattern import PatternConfidence
from schemas.pattern import PatternDetectionRequest
from schemas.pattern import PatternDetectionResult as PatternDetectionResultSchema
from services.pattern_detection import detect_pattern

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.post(
    "/detect",
    response_model=PatternDetectionResultSchema,
    summary="Preview chapter pattern detection for a URL",
    description=(
        "Analyse a URL and return the detected chapter template and regex. "
        "Supply `manual_regex` (with one capture group) to override auto-detection. "
        "This endpoint is read-only and does not create or modify any tracked items."
    ),
)
def detect(payload: PatternDetectionRequest):
    try:
        result = detect_pattern(payload.url, payload.manual_regex)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return PatternDetectionResultSchema(
        url_template=result.url_template,
        chapter_regex=result.chapter_regex,
        current_chapter=result.current_chapter,
        confidence=PatternConfidence(result.confidence.value),
        strategy_used=result.strategy_used,
        pattern_source=result.pattern_source,
    )
