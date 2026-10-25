"""Numerical geometry for CalculusWeb.

The functions in this module deliberately distinguish between:

* the *capture order* of a freehand trace, which is needed to validate that the
  drawing represents a single-valued function, and
* the *x order* required by the trapezoid rule.

No assumption is made about the canvas origin or pixel scale: the frontend
already converts canvas coordinates to mathematical coordinates before sending
points to the API.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from typing import Iterable, Sequence

from math_engine import CompiledExpression, ExpressionEvaluationError

EPS = 1e-12
MAX_INTEGRATION_POINTS = 5000
MAX_CURVE_SAMPLES = 5000


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _distance(a: dict, b: dict) -> float:
    return math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))


def _dedupe_consecutive(points: Sequence[dict], tolerance: float = 1e-9) -> list[dict]:
    out: list[dict] = []
    for point in points:
        if not out or _distance(out[-1], point) > tolerance:
            out.append({"x": float(point["x"]), "y": float(point["y"])})
    return out


def remove_duplicates(points: Sequence[dict]) -> list[dict]:
    if not points:
        return []
    result = [{"x": float(points[0]["x"]), "y": float(points[0]["y"])}]
    for current in points[1:]:
        last = result[-1]
        if (
            abs(float(current["x"]) - last["x"]) > 1e-6
            or abs(float(current["y"]) - last["y"]) > 1e-6
        ):
            result.append({"x": float(current["x"]), "y": float(current["y"])})
    return result


def remove_close_points(points: Sequence[dict]) -> list[dict]:
    if len(points) < 2:
        return [{"x": float(p["x"]), "y": float(p["y"])} for p in points]
    result = [{"x": float(points[0]["x"]), "y": float(points[0]["y"])}]
    for current in points[1:]:
        last = result[-1]
        dx = float(current["x"]) - last["x"]
        dy = float(current["y"]) - last["y"]
        if dx * dx + dy * dy >= 1e-12:
            result.append({"x": float(current["x"]), "y": float(current["y"])})
    return result


def simplify_curve(points: Sequence[dict], max_points: int = 500) -> list[dict]:
    if len(points) <= max_points:
        return [{"x": float(p["x"]), "y": float(p["y"])} for p in points]
    step = max(1, math.ceil((len(points) - 1) / (max_points - 1)))
    result = [
        {"x": float(points[i]["x"]), "y": float(points[i]["y"])}
        for i in range(0, len(points), step)
    ]
    last = {"x": float(points[-1]["x"]), "y": float(points[-1]["y"])}
    if result[-1] != last:
        result.append(last)
    return result


def sort_by_x(points: Sequence[dict]) -> list[dict]:
    return sorted(
        ({"x": float(p["x"]), "y": float(p["y"])} for p in points),
        key=lambda p: p["x"],
    )


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


# ---------------------------------------------------------------------------
# Drawing validation
# ---------------------------------------------------------------------------


def _orientation(a: dict, b: dict, c: dict) -> float:
    return (b["x"] - a["x"]) * (c["y"] - a["y"]) - (b["y"] - a["y"]) * (
        c["x"] - a["x"]
    )


def _on_segment(a: dict, b: dict, p: dict, tolerance: float) -> bool:
    return (
        min(a["x"], b["x"]) - tolerance <= p["x"] <= max(a["x"], b["x"]) + tolerance
        and min(a["y"], b["y"]) - tolerance <= p["y"] <= max(a["y"], b["y"]) + tolerance
    )


def _segments_intersect(
    a1: dict, a2: dict, b1: dict, b2: dict, tolerance: float
) -> bool:
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)
    scale = max(
        abs(a2["x"] - a1["x"]) + abs(a2["y"] - a1["y"]),
        abs(b2["x"] - b1["x"]) + abs(b2["y"] - b1["y"]),
        1.0,
    )
    eps = tolerance * scale

    if o1 * o2 < -eps and o3 * o4 < -eps:
        return True
    if abs(o1) <= eps and _on_segment(a1, a2, b1, tolerance):
        return True
    if abs(o2) <= eps and _on_segment(a1, a2, b2, tolerance):
        return True
    if abs(o3) <= eps and _on_segment(b1, b2, a1, tolerance):
        return True
    if abs(o4) <= eps and _on_segment(b1, b2, a2, tolerance):
        return True
    return False


def _self_intersection(
    points: Sequence[dict], x_span: float, tolerance: float
) -> tuple[bool, float | None]:
    """Find a self-intersection between non-adjacent segments.

    The check is bounded to 1200 points.  For big traces we keep evenly spaced
    points, which is enough to preserve large loops while avoiding O(n²) work.
    """

    if len(points) < 5:
        return False, None
    if len(points) > 1200:
        step = max(1, len(points) // 1200)
        sampled = list(points[::step])
        if sampled[-1] is not points[-1]:
            sampled.append(points[-1])
        points = sampled

    segments = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if abs(a["x"] - b["x"]) < tolerance and abs(a["y"] - b["y"]) < tolerance:
            continue
        segments.append((min(a["x"], b["x"]), max(a["x"], b["x"]), i, a, b))
    segments.sort(key=lambda s: s[0])

    for pos, seg in enumerate(segments):
        _, max_x, i, a1, a2 = seg
        for other in segments[pos + 1 :]:
            min_x2, _, j, b1, b2 = other
            if min_x2 > max_x + tolerance:
                break
            if abs(i - j) <= 1:
                continue
            # Curves that close on themselves share the first/last vertex; do
            # not report that single shared endpoint as a crossing.
            shared = 0
            for p in (a1, a2):
                for q in (b1, b2):
                    if _distance(p, q) <= tolerance * max(1.0, x_span):
                        shared += 1
            if shared:
                continue
            if _segments_intersect(a1, a2, b1, b2, tolerance):
                return True, min(a1["x"], a2["x"], b1["x"], b2["x"])
    return False, None


def _ambiguous_bins(
    points: Sequence[dict], x_span: float, y_span: float
) -> list[dict]:
    """Detect two separated y branches sharing an x range."""

    bins = min(48, max(8, int(math.sqrt(max(len(points), 1)) * 1.5)))
    width = x_span / bins if bins else x_span
    if width <= 0:
        return []

    buckets: list[list[dict]] = [[] for _ in range(bins)]
    min_x = min(p["x"] for p in points)
    for point in points:
        idx = min(bins - 1, max(0, int((point["x"] - min_x) / width)))
        buckets[idx].append(point)

    regions: list[dict] = []
    gap_threshold = max(0.12 * y_span, 1e-9)
    for idx, bucket in enumerate(buckets):
        if len(bucket) < 6:
            continue
        ordered = sorted(bucket, key=lambda p: p["y"])
        largest_gap = 0.0
        split_at = -1
        for i in range(1, len(ordered)):
            gap = ordered[i]["y"] - ordered[i - 1]["y"]
            if gap > largest_gap:
                largest_gap = gap
                split_at = i
        if split_at < 3 or len(ordered) - split_at < 3:
            continue
        if largest_gap < gap_threshold:
            continue

        lower = ordered[:split_at]
        upper = ordered[split_at:]
        low_min = min(p["x"] for p in lower)
        low_max = max(p["x"] for p in lower)
        high_min = min(p["x"] for p in upper)
        high_max = max(p["x"] for p in upper)
        overlap = min(low_max, high_max) - max(low_min, high_min)
        if overlap <= 0.15 * width:
            continue

        start = min_x + idx * width
        end = start + width
        regions.append(
            {
                "start": start,
                "end": end,
                "reason": "MULTIPLE_Y_FOR_X",
                "detail": "Dos ramas de la curva comparten el mismo rango de X.",
            }
        )
    return regions


def validate_drawing(points: Sequence[dict]) -> dict:
    """Classify a captured trace as a candidate for y = f(x).

    The result is deliberately three-valued: ``valid``, ``invalid`` or
    ``uncertain``.  A finite noisy drawing cannot prove a property of a
    continuous mathematical curve, so the criteria and diagnostics are always
    returned.
    """

    raw = [
        {"x": float(p["x"]), "y": float(p["y"])}
        for p in points
        if _finite(p.get("x")) and _finite(p.get("y"))
    ]
    if len(raw) != len(points):
        return {
            "status": "invalid",
            "is_function": False,
            "reason_code": "INVALID_COORDINATES",
            "message": "El dibujo contiene coordenadas no finitas (NaN o Infinity).",
            "diagnostics": {
                "point_count": len(points),
                "finite_point_count": len(raw),
                "ambiguous_regions": [],
                "criteria": ["Todas las coordenadas deben ser números reales finitos."],
            },
        }

    cleaned = _dedupe_consecutive(raw)
    n = len(cleaned)
    if n == 0:
        return _validation_result(
            "invalid",
            False,
            "NO_POINTS",
            "No hay puntos para analizar.",
            {"point_count": 0},
        )
    if n < 8:
        return _validation_result(
            "uncertain",
            False,
            "INSUFFICIENT_POINTS",
            "El trazo tiene muy pocos puntos para validarlo con seguridad. Dibuja una curva más larga o vuelve a intentarlo.",
            {"point_count": n, "minimum_points": 8},
        )

    xs = [p["x"] for p in cleaned]
    ys = [p["y"] for p in cleaned]
    x_span = max(xs) - min(xs)
    y_span = max(ys) - min(ys)
    diagonal = math.hypot(x_span, y_span)
    if x_span <= max(1e-9, 0.002 * max(diagonal, 1e-9)):
        return _validation_result(
            "invalid",
            False,
            "VERTICAL_TRACE",
            "El trazo es casi vertical: no representa una función y = f(x), porque un mismo X tendría infinitos valores de Y.",
            {
                "point_count": n,
                "x_span": x_span,
                "y_span": y_span,
            },
        )

    dxs = [cleaned[i + 1]["x"] - cleaned[i]["x"] for i in range(n - 1)]
    abs_dx = [abs(dx) for dx in dxs if abs(dx) > EPS]
    median_dx = _median(abs_dx) or x_span / max(n - 1, 1)
    significant_dx = max(median_dx * 0.5, x_span * 0.0005, 1e-12)

    positive_dx = sum(dx for dx in dxs if dx > significant_dx)
    negative_dx = sum(-dx for dx in dxs if dx < -significant_dx)
    total_dx = positive_dx + negative_dx
    backtrack_ratio = (
        min(positive_dx, negative_dx) / total_dx if total_dx > 0 else 0.0
    )

    reversals = 0
    last_sign = 0
    for dx in dxs:
        if abs(dx) <= significant_dx:
            continue
        sign = 1 if dx > 0 else -1
        if last_sign and sign != last_sign:
            reversals += 1
        last_sign = sign

    gaps = [
        i
        for i in range(n - 1)
        if _distance(cleaned[i], cleaned[i + 1])
        > max(10.0 * median_dx, 0.06 * max(diagonal, 1e-9))
    ]

    steep = 0
    for i in range(n - 1):
        dx = abs(dxs[i])
        dy = abs(cleaned[i + 1]["y"] - cleaned[i]["y"])
        if dy > 1e-9 and (dx < 1e-12 or dy / max(dx, 1e-12) > 80.0):
            steep += 1

    noise_ratio = 0.0
    if n >= 5 and y_span > 1e-9:
        residuals = []
        for i in range(1, n - 1):
            midpoint = (cleaned[i - 1]["y"] + cleaned[i + 1]["y"]) / 2.0
            residuals.append(abs(cleaned[i]["y"] - midpoint))
        noise_ratio = _median(residuals) / y_span

    ambiguous_regions = _ambiguous_bins(cleaned, x_span, y_span)
    self_crosses, crossing_x = _self_intersection(
        cleaned, x_span, tolerance=max(1e-9, x_span * 1e-7)
    )
    if self_crosses:
        ambiguous_regions.insert(
            0,
            {
                "start": crossing_x if crossing_x is not None else min(xs),
                "end": crossing_x if crossing_x is not None else max(xs),
                "reason": "SELF_INTERSECTION",
                "detail": "El trazo se cruza a sí mismo, por lo que hay X con varios Y.",
            },
        )

    diagnostics = {
        "point_count": len(points),
        "unique_point_count": n,
        "x_span": round(x_span, 10),
        "y_span": round(y_span, 10),
        "direction": (
            "increasing"
            if positive_dx > negative_dx * 5
            else "decreasing"
            if negative_dx > positive_dx * 5
            else "mixed"
        ),
        "backtrack_ratio": round(backtrack_ratio, 6),
        "reversals": reversals,
        "gaps": len(gaps),
        "steep_segments": steep,
        "noise_ratio": round(noise_ratio, 6),
        "self_intersections": 1 if self_crosses else 0,
        "ambiguous_regions": ambiguous_regions,
        "criteria": [
            "Se conserva el orden de captura para validar la geometría.",
            "Se ignoran pequeñas reversiones compatibles con ruido de entrada.",
            "Un trazo es función si cada X del intervalo tiene un único Y razonable.",
            "La validación es numérica y heurística; no demuestra propiedades de una curva continua.",
        ],
    }

    # Strong evidence against a single-valued function.
    if backtrack_ratio > 0.15 and positive_dx > 0.05 * x_span and negative_dx > 0.05 * x_span:
        diagnostics["ambiguous_regions"] = diagnostics["ambiguous_regions"] or [
            {
                "start": min(xs),
                "end": max(xs),
                "reason": "BACKTRACKING",
                "detail": "El trazo retrocede sobre un rango amplio de X.",
            }
        ]
        return _validation_result(
            "invalid",
            False,
            "MULTIPLE_Y_FOR_X",
            "Este dibujo no representa una función única y = f(x): el trazo retrocede y hay valores de X asociados a varios valores de Y.",
            diagnostics,
        )
    if ambiguous_regions and any(
        region["reason"] == "MULTIPLE_Y_FOR_X" for region in ambiguous_regions
    ):
        return _validation_result(
            "invalid",
            False,
            "MULTIPLE_Y_FOR_X",
            "Este dibujo no representa una función única y = f(x): hay regiones con varios valores de Y para un mismo X.",
            diagnostics,
        )
    if self_crosses:
        return _validation_result(
            "invalid",
            False,
            "SELF_INTERSECTION",
            "El trazo se cruza a sí mismo. Una función y = f(x) no puede tener dos valores de Y para el mismo X.",
            diagnostics,
        )

    # Ambiguous evidence: do not silently accept it as a function.
    if gaps:
        return _validation_result(
            "uncertain",
            False,
            "DISCONTINUOUS_TRACE",
            "El trazo parece tener saltos o varios trazos separados. No se unirán automáticamente; corrige el dibujo o usa el modo función.",
            diagnostics,
        )
    if backtrack_ratio > 0.05 or reversals >= 3:
        return _validation_result(
            "uncertain",
            False,
            "BACKTRACKING",
            "El trazo retrocede varias veces. Puede ser ruido o una curva que no es una función; no se calculará el área sin confirmación.",
            diagnostics,
        )
    if steep >= max(3, int(0.04 * n)) and x_span < diagonal * 0.25:
        return _validation_result(
            "uncertain",
            False,
            "STEEP_SEGMENTS",
            "Hay demasiados segmentos casi verticales. La escala del dibujo no permite validar una función con seguridad.",
            diagnostics,
        )
    if noise_ratio > 0.08:
        return _validation_result(
            "uncertain",
            False,
            "NOISY_TRACE",
            "El trazo tiene demasiado ruido para distinguir una función con seguridad. Intenta dibujar con un movimiento más continuo.",
            diagnostics,
        )

    return _validation_result(
        "valid",
        True,
        "OK",
        "El dibujo es compatible con una función única y = f(x) en el intervalo observado.",
        diagnostics,
    )


def _validation_result(
    status: str, is_function: bool, reason_code: str, message: str, diagnostics: dict
) -> dict:
    diagnostics = dict(diagnostics)
    diagnostics.setdefault("ambiguous_regions", [])
    diagnostics.setdefault("criteria", [])
    return {
        "status": status,
        "is_function": is_function,
        "reason_code": reason_code,
        "message": message,
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# Trapezoid integration (including x-axis splits)
# ---------------------------------------------------------------------------


def find_x_axis_intersections(points: Sequence[dict]) -> list[dict]:
    points = sort_by_x(points)
    intersections: list[dict] = []
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        if p1["y"] == 0.0:
            intersections.append({"x": p1["x"], "y": 0.0})
        if p1["y"] * p2["y"] < 0:
            dx = p2["x"] - p1["x"]
            if abs(p2["y"] - p1["y"]) < EPS:
                x = (p1["x"] + p2["x"]) / 2.0
            else:
                x = p1["x"] - p1["y"] * dx / (p2["y"] - p1["y"])
            intersections.append({"x": x, "y": 0.0})
    if points and points[-1]["y"] == 0.0:
        intersections.append({"x": points[-1]["x"], "y": 0.0})

    unique: list[dict] = []
    seen: set[float] = set()
    for point in sorted(intersections, key=lambda p: p["x"]):
        key = round(point["x"], 10)
        if key not in seen:
            seen.add(key)
            unique.append(point)
    return unique


def split_curve_at_intersections(
    points: Sequence[dict], intersections: Sequence[dict]
) -> list[list[dict]]:
    """Return x-ordered segments split at the supplied axis crossings."""

    if not intersections:
        return [sort_by_x(points)]
    merged = sort_by_x(list(points) + list(intersections))
    # Remove exact duplicates caused by an intersection already in points.
    cleaned: list[dict] = []
    for point in merged:
        if not cleaned or abs(cleaned[-1]["x"] - point["x"]) > 1e-10:
            cleaned.append(point)
    segments: list[list[dict]] = []
    current: list[dict] = []
    crossing_keys = {round(p["x"], 10) for p in intersections}
    for point in cleaned:
        current.append(point)
        if round(point["x"], 10) in crossing_keys and len(current) > 1:
            segments.append(current)
            current = [point]
    if len(current) > 1:
        segments.append(current)
    return segments


def integrate_points(points: Sequence[dict]) -> dict:
    """Integrate a point trace with the trapezoid rule.

    Consecutive points with opposite Y signs are split at their interpolated
    x-axis crossing.  This keeps signed integrals unchanged while making the
    positive/negative areas geometrically correct.
    """

    if len(points) < 2:
        raise ValueError("Se necesitan al menos 2 puntos para calcular el área.")

    cleaned = remove_duplicates(points)
    cleaned = remove_close_points(cleaned)
    cleaned = simplify_curve(cleaned, max_points=MAX_INTEGRATION_POINTS)
    cleaned = sort_by_x(cleaned)

    if all(abs(p["x"] - cleaned[0]["x"]) < 1e-12 for p in cleaned):
        raise ValueError("La curva es completamente vertical. No se puede calcular el área.")
    for point in cleaned:
        if not _finite(point["x"]) or not _finite(point["y"]):
            raise ValueError("Los puntos contienen valores inválidos (NaN o Infinity).")

    intersections = find_x_axis_intersections(cleaned)
    processed = list(cleaned)
    for crossing in intersections:
        x = crossing["x"]
        if all(abs(p["x"] - x) > 1e-10 for p in processed):
            processed.append({"x": x, "y": 0.0})
    processed = sort_by_x(processed)

    signed_integral = 0.0
    positive_area = 0.0
    negative_area = 0.0
    for i in range(len(processed) - 1):
        p1, p2 = processed[i], processed[i + 1]
        dx = p2["x"] - p1["x"]
        if abs(dx) < 1e-12:
            continue
        # A segment containing an inserted crossing has one endpoint at y=0,
        # so this formula is exact for both pieces.
        area = (p1["y"] + p2["y"]) / 2.0 * dx
        signed_integral += area
        if area >= 0:
            positive_area += area
        else:
            negative_area += area

    total_geometric_area = positive_area + abs(negative_area)
    return {
        "signed_integral": signed_integral,
        "positive_area": positive_area,
        "negative_area": negative_area,
        "total_geometric_area": total_geometric_area,
        "processed_points": processed,
        "x_axis_intersections": intersections,
        "has_valid_result": all(
            math.isfinite(v)
            for v in (
                signed_integral,
                positive_area,
                negative_area,
                total_geometric_area,
            )
        ),
    }


# ---------------------------------------------------------------------------
# Area between two curves
# ---------------------------------------------------------------------------


def _eval_pair(
    f: CompiledExpression, g: CompiledExpression, x: float
) -> tuple[float, float, float]:
    try:
        fv = f.evaluate(x)
        gv = g.evaluate(x)
    except ExpressionEvaluationError as exc:
        raise ExpressionEvaluationError(
            f"No se pudo evaluar una función en x = {x:.6g}: {exc}", x=x
        ) from exc
    if not math.isfinite(fv) or not math.isfinite(gv):
        raise ExpressionEvaluationError(
            f"Una función produce un valor no finito en x = {x:.6g}.", x=x
        )
    return fv, gv, fv - gv


def _refine_root(
    f: CompiledExpression,
    g: CompiledExpression,
    left: float,
    right: float,
    f_left: float,
    f_right: float,
) -> float:
    for _ in range(80):
        mid = (left + right) / 2.0
        _, _, h_mid = _eval_pair(f, g, mid)
        if abs(h_mid) < 1e-14:
            return mid
        if f_left * h_mid <= 0:
            right = mid
            f_right = h_mid
        else:
            left = mid
            f_left = h_mid
    return (left + right) / 2.0


def _dedupe_roots(roots: Iterable[float], tolerance: float) -> list[float]:
    out: list[float] = []
    for root in sorted(roots):
        if not out or abs(root - out[-1]) > tolerance:
            out.append(root)
    return out


def area_between_curves(
    f: CompiledExpression,
    g: CompiledExpression,
    start: float,
    end: float,
    samples: int = 1000,
) -> dict:
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("Los límites deben ser números finitos.")
    if start >= end:
        raise ValueError("El inicio del intervalo debe ser menor que el fin.")
    if end - start > 1e6:
        raise ValueError("El intervalo es demasiado amplio.")
    if not 2 <= samples <= MAX_CURVE_SAMPLES:
        raise ValueError(f"El número de muestras debe estar entre 2 y {MAX_CURVE_SAMPLES}.")

    step = (end - start) / samples
    xs = [start + i * step for i in range(samples + 1)]
    f_vals: list[float] = []
    g_vals: list[float] = []
    h_vals: list[float] = []
    for x in xs:
        fv, gv, h = _eval_pair(f, g, x)
        f_vals.append(fv)
        g_vals.append(gv)
        h_vals.append(h)

    y_values = f_vals + g_vals
    y_scale = max(max(y_values) - min(y_values), 1.0)
    root_tolerance = 1e-9 * max(abs(end - start), y_scale, 1.0)
    roots: list[float] = []

    for i, h in enumerate(h_vals):
        if abs(h) <= root_tolerance:
            roots.append(xs[i])
    for i in range(len(xs) - 1):
        h1, h2 = h_vals[i], h_vals[i + 1]
        if h1 * h2 < 0:
            roots.append(_refine_root(f, g, xs[i], xs[i + 1], h1, h2))

    roots = _dedupe_roots(roots, tolerance=max(1e-9, (end - start) * 1e-9))
    boundaries = [start] + [r for r in roots if start < r < end] + [end]
    boundaries = _dedupe_roots(boundaries, tolerance=max(1e-9, (end - start) * 1e-9))

    intersections = [{"x": root, "y": float(f.evaluate(root))} for root in roots]

    intervals: list[dict] = []
    evaluations = len(xs) * 2
    for i in range(len(boundaries) - 1):
        a, b = boundaries[i], boundaries[i + 1]
        if b - a <= 1e-14:
            continue
        fraction = (b - a) / (end - start)
        sub_samples = max(2, min(MAX_CURVE_SAMPLES, int(math.ceil(samples * fraction))))
        sub_step = (b - a) / sub_samples
        area = 0.0
        signed = 0.0
        prev_f, prev_g, prev_h = _eval_pair(f, g, a)
        for j in range(1, sub_samples + 1):
            x = a + sub_step * j
            cur_f, cur_g, cur_h = _eval_pair(f, g, x)
            dx = x - (a + sub_step * (j - 1))
            area += abs((prev_h + cur_h) / 2.0 * dx)
            signed += (prev_h + cur_h) / 2.0 * dx
            prev_f, prev_g, prev_h = cur_f, cur_g, cur_h
            evaluations += 2
        midpoint = (a + b) / 2.0
        _, _, mid_h = _eval_pair(f, g, midpoint)
        above = "f" if mid_h > 0 else "g" if mid_h < 0 else "equal"
        intervals.append(
            {
                "start": a,
                "end": b,
                "area": area,
                "signed_area": signed,
                "above": above,
            }
        )

    total_area = sum(interval["area"] for interval in intervals)
    signed_integral = sum(interval["signed_area"] for interval in intervals)

    # Merge roots into the displayed curves so the shaded polygons close at
    # every crossing instead of approximating the intersection crudely.
    display_x = sorted(set(xs + roots))
    f_points: list[dict] = []
    g_points: list[dict] = []
    for x in display_x:
        fv, gv, _ = _eval_pair(f, g, x)
        f_points.append({"x": x, "y": fv})
        g_points.append({"x": x, "y": gv})

    warnings: list[str] = []
    if not roots:
        warnings.append("Las curvas no se cruzan dentro del intervalo; se calcula una sola región.")
    if samples < 200:
        warnings.append("El muestreo es bajo; podrían no detectarse cruces muy próximos.")
    warnings.append(
        "El área se aproxima con la regla del trapecio y búsqueda de raíces por cambio de signo."
    )

    return {
        "total_area": total_area,
        "signed_integral": signed_integral,
        "start": start,
        "end": end,
        "samples_used": samples,
        "evaluations": evaluations,
        "method": "trapezoid + bisection",
        "intersections": intersections,
        "intervals": intervals,
        "f_points": f_points,
        "g_points": g_points,
        "warnings": warnings,
    }
