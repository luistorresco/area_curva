from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import numpy as np
from math import isfinite

app = FastAPI(title="Calculus API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Point(BaseModel):
    x: float
    y: float


class CurveRequest(BaseModel):
    points: List[Point]


class CalculationResult(BaseModel):
    signed_integral: float
    positive_area: float
    negative_area: float
    total_geometric_area: float
    processed_points: List[Point]
    x_axis_intersections: List[Point]
    has_valid_result: bool


def remove_duplicates(points: List[Point]) -> List[Point]:
    if not points:
        return []
    result = [points[0]]
    for i in range(1, len(points)):
        current = points[i]
        last = result[-1]
        if abs(current.x - last.x) > 1e-6 or abs(current.y - last.y) > 1e-6:
            result.append(current)
    return result


def remove_close_points(points: List[Point]) -> List[Point]:
    if len(points) < 2:
        return points
    result = [points[0]]
    for i in range(1, len(points)):
        current = points[i]
        last = result[-1]
        dx = current.x - last.x
        dy = current.y - last.y
        if dx * dx + dy * dy >= 1e-12:
            result.append(current)
    return result


def simplify_curve(points: List[Point], max_points: int = 500) -> List[Point]:
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) // (max_points - 1)
    result = []
    for i in range(0, len(points), step):
        result.append(points[i])
    if result[-1] != points[-1]:
        result.append(points[-1])
    return result


def ensure_monotonic_x(points: List[Point]) -> List[Point]:
    return sorted(points, key=lambda p: p.x)


def find_x_axis_intersections(points: List[Point]) -> List[Point]:
    intersections = []
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        
        if p1.y == 0.0 and p2.y == 0.0:
            continue
        if p1.y == 0.0:
            intersections.append(Point(x=p1.x, y=0.0))
            continue
        if p2.y == 0.0:
            intersections.append(Point(x=p2.x, y=0.0))
            continue
            
        if p1.y * p2.y < 0:
            x1, y1 = p1.x, p1.y
            x2, y2 = p2.x, p2.y
            
            if abs(y2 - y1) < 1e-12:
                x_intersect = (x1 + x2) / 2.0
            else:
                t = -y1 / (y2 - y1)
                x_intersect = x1 + t * (x2 - x1)
            
            intersections.append(Point(x=x_intersect, y=0.0))
    
    unique = []
    seen = set()
    for p in intersections:
        key = round(p.x, 10)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return sorted(unique, key=lambda p: p.x)


def split_curve_at_intersections(points: List[Point], intersections: List[Point]) -> List[List[Point]]:
    if not intersections:
        return [points]
    
    all_points = points + intersections
    all_points.sort(key=lambda p: p.x)
    
    segments = []
    current_segment = []
    
    for point in all_points:
        current_segment.append(point)
        is_intersection = any(abs(p.x - point.x) < 1e-10 and abs(p.y - point.y) < 1e-10 for p in intersections)
        if is_intersection and len(current_segment) > 1:
            segments.append(current_segment)
            current_segment = [point]
    
    if len(current_segment) > 1:
        segments.append(current_segment)
    
    return [s for s in segments if len(s) >= 2]


def trapezoid_area(p1: Point, p2: Point) -> float:
    dx = p2.x - p1.x
    if abs(dx) < 1e-12:
        return 0.0
    return ((p1.y + p2.y) / 2.0) * dx


def validate_curve(points: List[Point]) -> Optional[str]:
    if not points:
        return "No hay puntos para calcular."
    if len(points) < 2:
        return "Se necesitan al menos 2 puntos para calcular el área."
    
    unique_x = set(round(p.x, 10) for p in points)
    if len(unique_x) == 1:
        return "La curva es completamente vertical. No se puede calcular el área."
    
    for p in points:
        if not isfinite(p.x) or not isfinite(p.y):
            return "Los puntos contienen valores inválidos (NaN o Infinity)."
    
    return None


@app.post("/api/calculate", response_model=CalculationResult)
async def calculate_area(request: CurveRequest):
    error = validate_curve(request.points)
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    points = remove_duplicates(request.points)
    points = remove_close_points(points)
    points = simplify_curve(points)
    points = ensure_monotonic_x(points)
    
    intersections = find_x_axis_intersections(points)
    
    signed_integral = 0.0
    positive_area = 0.0
    negative_area = 0.0
    
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        area = trapezoid_area(p1, p2)
        signed_integral += area
        
        if area >= 0:
            positive_area += area
        else:
            negative_area += area
    
    total_geometric_area = positive_area + abs(negative_area)
    
    return CalculationResult(
        signed_integral=signed_integral,
        positive_area=positive_area,
        negative_area=negative_area,
        total_geometric_area=total_geometric_area,
        processed_points=points,
        x_axis_intersections=intersections,
        has_valid_result=isfinite(signed_integral) and isfinite(positive_area) and isfinite(negative_area) and isfinite(total_geometric_area)
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)