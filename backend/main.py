"""FastAPI routes for CalculusWeb.

The route layer is intentionally thin: parsing and numerical algorithms live in
``math_engine``, ``curve_math`` and ``recognition``.  Endpoints are synchronous
``def`` functions so CPU-bound numerical work runs in FastAPI's thread pool
instead of blocking the event loop.
"""

from __future__ import annotations

import math
import os
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from curve_math import (
    MAX_CURVE_SAMPLES,
    MAX_INTEGRATION_POINTS,
    area_between_curves,
    integrate_points,
    validate_drawing as validate_drawing_points,
)
from math_engine import (
    MAX_EXPRESSION_LENGTH,
    ExpressionError,
    compile_expression,
    sample_expression,
)
from recognition import recognize_function
from schemas import (
    AreaBetweenRequest,
    AreaBetweenResponse,
    CalculationResult,
    CurveRequest,
    DrawingValidation,
    FunctionRequest,
    RecognitionResponse,
    Point,
    VolumeProfileRequest,
    VolumeRequest,
    VolumeResponse,
)
from volume_math import volume_from_profile, volume_solid

MAX_EVALUATION_SAMPLES = 2000
MAX_RECOGNITION_POINTS = 5000

app = FastAPI(
    title="Calculus API",
    version="2.0.0",
    description="Validación de dibujos, reconocimiento de funciones, integración y área entre curvas.",
)

_raw_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:4321,http://127.0.0.1:4321"
)
_origins = [origin.strip() for origin in _raw_origins.split(",") if origin.strip()]
_allow_all_origins = "*" in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all_origins else _origins,
    allow_credentials=not _allow_all_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _points(points: List[Point]) -> list[dict]:
    return [{"x": p.x, "y": p.y} for p in points]


def _check_interval(start: float, end: float) -> None:
    if not math.isfinite(start) or not math.isfinite(end):
        raise HTTPException(status_code=400, detail="Los límites del intervalo deben ser números finitos.")
    if start >= end:
        raise HTTPException(status_code=400, detail="El inicio del intervalo debe ser menor que el fin.")
    if end - start > 1e6:
        raise HTTPException(status_code=400, detail="El intervalo es demasiado amplio.")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/validate-drawing", response_model=DrawingValidation)
def validate_drawing(request: CurveRequest) -> dict:
    if len(request.points) > MAX_INTEGRATION_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"El dibujo supera el máximo de {MAX_INTEGRATION_POINTS} puntos.",
        )
    return validate_drawing_points(_points(request.points))


@app.post("/api/calculate", response_model=CalculationResult)
def calculate_area(request: CurveRequest) -> dict:
    if len(request.points) > MAX_INTEGRATION_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"El cálculo admite como máximo {MAX_INTEGRATION_POINTS} puntos.",
        )
    try:
        return integrate_points(_points(request.points))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/evaluate-function")
def evaluate_function(request: FunctionRequest) -> dict:
    expression = (request.expression or "").strip()
    if not expression:
        raise HTTPException(status_code=400, detail="La expresión está vacía.")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"La expresión es demasiado larga (máximo {MAX_EXPRESSION_LENGTH} caracteres).",
        )
    _check_interval(request.start, request.end)
    if not 2 <= request.samples <= MAX_EVALUATION_SAMPLES:
        raise HTTPException(
            status_code=400,
            detail=f"El número de muestras debe estar entre 2 y {MAX_EVALUATION_SAMPLES}.",
        )

    try:
        compiled = compile_expression(expression)
        points = sample_expression(compiled, request.start, request.end, request.samples)
    except ExpressionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "expression": expression,
        "start": request.start,
        "end": request.end,
        "points": points,
    }


@app.post("/api/recognize-function", response_model=RecognitionResponse)
def recognize(request: CurveRequest) -> dict:
    if len(request.points) > MAX_RECOGNITION_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"El reconocimiento admite como máximo {MAX_RECOGNITION_POINTS} puntos.",
        )
    return recognize_function(_points(request.points))


@app.post("/api/area-between-curves", response_model=AreaBetweenResponse)
def area_between(request: AreaBetweenRequest) -> dict:
    _check_interval(request.start, request.end)
    if not 2 <= request.samples <= MAX_CURVE_SAMPLES:
        raise HTTPException(
            status_code=400,
            detail=f"El número de muestras debe estar entre 2 y {MAX_CURVE_SAMPLES}.",
        )
    if len(request.f_expression or "") > MAX_EXPRESSION_LENGTH or len(
        request.g_expression or ""
    ) > MAX_EXPRESSION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Cada expresión admite como máximo {MAX_EXPRESSION_LENGTH} caracteres.",
        )

    try:
        f_compiled = compile_expression(request.f_expression)
        g_compiled = compile_expression(request.g_expression)
        result = area_between_curves(
            f_compiled,
            g_compiled,
            request.start,
            request.end,
            request.samples,
        )
    except ExpressionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@app.post("/api/volume", response_model=VolumeResponse)
def volume(request: VolumeRequest) -> dict:
    """Volume of a solid of revolution (discs, washers or shells)."""

    _check_interval(request.start, request.end)
    if len(request.f_expression or "") > MAX_EXPRESSION_LENGTH or len(
        request.g_expression or ""
    ) > MAX_EXPRESSION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Cada expresión admite como máximo {MAX_EXPRESSION_LENGTH} caracteres.",
        )
    if not request.f_expression.strip():
        raise HTTPException(status_code=400, detail="La expresión de la función está vacía.")

    try:
        return volume_solid(
            method=request.method,
            axis=request.axis,
            f_expression=request.f_expression,
            g_expression=request.g_expression,
            start=request.start,
            end=request.end,
            samples=request.samples,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/volume-profile", response_model=VolumeResponse)
def volume_profile(request: VolumeProfileRequest) -> dict:
    """Volume from the user's imported stroke/function.

    The actual points are used as the region boundary, so changing the
    method or the revolution axis keeps the user's drawing instead of
    reinterpreting an expression in the wrong variable.
    """

    if len(request.points) > MAX_RECOGNITION_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"El trazo admite como máximo {MAX_RECOGNITION_POINTS} puntos.",
        )
    if len(request.g_expression or "") > MAX_EXPRESSION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"La expresión de g admite como máximo {MAX_EXPRESSION_LENGTH} caracteres.",
        )

    try:
        return volume_from_profile(
            method=request.method,
            axis=request.axis,
            points=_points(request.points),
            g_expression=request.g_expression,
            start=request.start,
            end=request.end,
            samples=request.samples,
            f_expression=request.f_expression,
            source=request.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
