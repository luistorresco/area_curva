"""Pydantic contracts for the CalculusWeb API."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class CurveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: List[Point] = Field(..., min_length=1, max_length=5000)


class CalculationResult(BaseModel):
    signed_integral: float
    positive_area: float
    negative_area: float
    total_geometric_area: float
    processed_points: List[Point]
    x_axis_intersections: List[Point]
    has_valid_result: bool


class FunctionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str
    start: float
    end: float
    samples: int = 240


class DrawingValidation(BaseModel):
    status: Literal["valid", "invalid", "uncertain"]
    is_function: bool
    reason_code: str
    message: str
    diagnostics: Dict


class RecognitionCandidate(BaseModel):
    expression: str
    model: str
    method: str
    label: str
    complexity: int
    metrics: Dict[str, float]
    domain: Dict[str, float]
    warnings: List[str] = Field(default_factory=list)


class RecognitionResponse(BaseModel):
    status: Literal["success", "low_confidence", "no_fit", "invalid", "uncertain"]
    is_function: bool
    recognized: bool
    expression: Optional[str] = None
    method: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None
    domain: Optional[Dict[str, float]] = None
    confidence: Optional[str] = None
    candidates: List[RecognitionCandidate] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    validation: DrawingValidation


class AreaBetweenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    f_expression: str
    g_expression: str
    start: float
    end: float
    samples: int = 1000


class IntervalArea(BaseModel):
    start: float
    end: float
    area: float
    signed_area: float
    above: Literal["f", "g", "equal"]


class Intersection(BaseModel):
    x: float
    y: float


class AreaBetweenResponse(BaseModel):
    total_area: float
    signed_integral: float
    start: float
    end: float
    samples_used: int
    evaluations: int
    method: str
    intersections: List[Intersection]
    intervals: List[IntervalArea]
    f_points: List[Point]
    g_points: List[Point]
    warnings: List[str] = Field(default_factory=list)
