"""Local mathematical model recognition for hand-drawn curves.

The recognizer deliberately returns *candidates* with error metrics instead of
claiming that the original symbolic formula has been recovered.  All fits use
NumPy and the existing safe expression evaluator; no external AI service is
required.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

from curve_math import validate_drawing
from math_engine import ExpressionError, compile_expression

MAX_RECOGNITION_POINTS = 600
MAX_CANDIDATES = 5
HOLDOUT_MIN_POINTS = 30

_MODEL_LABELS = {
    "constant": "constante",
    "polynomial": "polinómica",
    "exponential": "exponencial",
    "logarithmic": "logarítmica",
    "radical": "radical",
    "absolute": "valor absoluto",
    "rational": "racional",
    "trigonometric": "trigonométrica",
    "logistic": "sigmoide",
}


def _num(value: float, digits: int = 6) -> str:
    if abs(value) < 1e-10:
        return "0"
    return f"{float(value):.{digits}g}"


def _shift(center: float) -> str:
    if abs(center) < 1e-9:
        return "x"
    if center > 0:
        return f"(x - {_num(center)})"
    return f"(x + {_num(-center)})"


def _linear_factor(coefficient: float, center: float) -> str:
    if abs(coefficient) < 1e-10:
        return "0"
    body = _shift(center)
    if abs(coefficient - 1.0) < 1e-10:
        return body
    if abs(coefficient + 1.0) < 1e-10:
        return f"-{body}"
    return f"{_num(coefficient)}*{body}"


def _format_polynomial(center: float, coefficients: dict[int, float]) -> str:
    """Format coefficients keyed by power in ``u = x - center``."""

    parts: list[str] = []
    u = _shift(center)
    for power in sorted(coefficients, reverse=True):
        coefficient = coefficients[power]
        if abs(coefficient) < 1e-9:
            continue
        magnitude = abs(coefficient)
        if power == 0:
            body = _num(magnitude)
        else:
            power_body = u if power == 1 else f"{u}**{power}"
            body = power_body if abs(magnitude - 1.0) < 1e-9 else f"{_num(magnitude)}*{power_body}"
        sign = "-" if coefficient < 0 else "+"
        parts.append((sign, body))

    if not parts:
        return "0"

    result = ("-" if parts[0][0] == "-" else "") + parts[0][1]
    for sign, body in parts[1:]:
        result += f" {sign} {body}"
    return result


def _metrics(predicted: np.ndarray, y: np.ndarray, y_scale: float) -> dict:
    residuals = predicted - y
    sse = float(np.sum(residuals * residuals))
    rmse = math.sqrt(sse / max(len(y), 1))
    max_error = float(np.max(np.abs(residuals))) if len(y) else 0.0
    relative = rmse / max(y_scale, 1e-9)
    centered = y - float(np.mean(y))
    sst = float(np.sum(centered * centered))
    r2 = 1.0 - sse / sst if sst > 1e-15 else (1.0 if sse < 1e-15 else 0.0)
    return {
        "rmse": rmse,
        "max_error": max_error,
        "relative_error": relative,
        "r2": r2,
    }


def _safe_lstsq(a: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    try:
        coefficients, *_ = np.linalg.lstsq(a, y, rcond=None)
    except (np.linalg.LinAlgError, ValueError):
        return None
    if not np.all(np.isfinite(coefficients)):
        return None
    return coefficients


def _polynomial_fit(x: np.ndarray, y: np.ndarray, degree: int) -> dict | None:
    if len(x) < degree + 1:
        return None
    center = float((np.min(x) + np.max(x)) / 2.0)
    scale = max(float((np.max(x) - np.min(x)) / 2.0), 1e-9)
    t = (x - center) / scale
    try:
        coeff_t = np.polyfit(t, y, degree)
    except (np.linalg.LinAlgError, ValueError, TypeError):
        return None
    if not np.all(np.isfinite(coeff_t)):
        return None
    # Convert from powers of t=(x-center)/scale to powers of (x-center).
    coefficients: dict[int, float] = {}
    for index, coefficient in enumerate(coeff_t):
        power = degree - index
        coefficients[power] = float(coefficient) / (scale**power)
    expression = _format_polynomial(center, coefficients)
    predicted = np.polyval(coeff_t, t)
    return {
        "key": f"poly_{degree}",
        "method": f"polynomial_degree_{degree}",
        "label": _MODEL_LABELS["polynomial"],
        "expression": expression,
        "complexity": degree + 1,
        "predicted": predicted,
    }


def _fit_constant(x: np.ndarray, y: np.ndarray) -> dict | None:
    value = float(np.mean(y))
    return {
        "key": "constant",
        "method": "constant_fit",
        "label": _MODEL_LABELS["constant"],
        "expression": _num(value),
        "complexity": 1,
        "predicted": np.full_like(y, value, dtype=float),
    }


def _fit_exponential(x: np.ndarray, y: np.ndarray) -> dict | None:
    span = max(float(np.max(x) - np.min(x)), 1e-6)
    center = float((np.min(x) + np.max(x)) / 2.0)
    best = None
    for b in np.linspace(-12.0 / span, 12.0 / span, 121):
        exponent = b * (x - center)
        if np.max(np.abs(exponent)) > 120:
            continue
        z = np.exp(exponent)
        a = np.column_stack([z, np.ones_like(z)])
        coefficients = _safe_lstsq(a, y)
        if coefficients is None:
            continue
        predicted = a @ coefficients
        error = float(np.sum((predicted - y) ** 2))
        if best is None or error < best[0]:
            best = (error, float(b), coefficients, predicted)
    if best is None:
        return None
    _, b, coefficients, predicted = best
    amplitude = coefficients[0]
    offset = coefficients[1]
    exp_body = f"exp({_linear_factor(b, center)})"
    if abs(amplitude - 1.0) < 1e-9:
        expression = exp_body
    elif abs(amplitude + 1.0) < 1e-9:
        expression = f"-{exp_body}"
    else:
        expression = f"{_num(amplitude)}*{exp_body}"
    if abs(offset) >= 1e-9:
        expression += f" {'+' if offset >= 0 else '-'} {_num(abs(offset))}"
    return {
        "key": "exponential",
        "method": "exponential_fit",
        "label": _MODEL_LABELS["exponential"],
        "expression": expression,
        "complexity": 4,
        "predicted": predicted,
    }


def _fit_logarithmic(x: np.ndarray, y: np.ndarray) -> dict | None:
    if np.min(x) <= 0:
        return None
    z = np.log(x)
    a = np.column_stack([z, np.ones_like(z)])
    coefficients = _safe_lstsq(a, y)
    if coefficients is None:
        return None
    predicted = a @ coefficients
    a1, b = float(coefficients[0]), float(coefficients[1])
    body = "log(x)"
    if abs(a1 - 1.0) < 1e-9:
        expression = body
    elif abs(a1 + 1.0) < 1e-9:
        expression = f"-{body}"
    else:
        expression = f"{_num(a1)}*{body}"
    if abs(b) >= 1e-9:
        expression += f" {'+' if b >= 0 else '-'} {_num(abs(b))}"
    return {
        "key": "logarithmic",
        "method": "logarithmic_fit",
        "label": _MODEL_LABELS["logarithmic"],
        "expression": expression,
        "complexity": 3,
        "predicted": predicted,
    }


def _fit_radical(x: np.ndarray, y: np.ndarray) -> dict | None:
    span = max(float(np.max(x) - np.min(x)), 1e-6)
    best = None
    for h in np.linspace(float(np.min(x)) - span, float(np.min(x)), 121):
        under = x - h
        if np.min(under) < -1e-12:
            continue
        z = np.sqrt(np.maximum(under, 0.0))
        a = np.column_stack([z, np.ones_like(z)])
        coefficients = _safe_lstsq(a, y)
        if coefficients is None:
            continue
        predicted = a @ coefficients
        error = float(np.sum((predicted - y) ** 2))
        if best is None or error < best[0]:
            best = (error, float(h), coefficients, predicted)
    if best is None:
        return None
    _, h, coefficients, predicted = best
    amplitude, offset = float(coefficients[0]), float(coefficients[1])
    body = f"sqrt({_shift(h)})"
    if abs(amplitude - 1.0) < 1e-9:
        expression = body
    elif abs(amplitude + 1.0) < 1e-9:
        expression = f"-{body}"
    else:
        expression = f"{_num(amplitude)}*{body}"
    if abs(offset) >= 1e-9:
        expression += f" {'+' if offset >= 0 else '-'} {_num(abs(offset))}"
    return {
        "key": "radical",
        "method": "radical_fit",
        "label": _MODEL_LABELS["radical"],
        "expression": expression,
        "complexity": 4,
        "predicted": predicted,
    }


def _fit_absolute(x: np.ndarray, y: np.ndarray) -> dict | None:
    span = max(float(np.max(x) - np.min(x)), 1e-6)
    best = None
    for h in np.linspace(float(np.min(x)) - 0.5 * span, float(np.max(x)) + 0.5 * span, 161):
        z = np.abs(x - h)
        a = np.column_stack([z, np.ones_like(z)])
        coefficients = _safe_lstsq(a, y)
        if coefficients is None:
            continue
        predicted = a @ coefficients
        error = float(np.sum((predicted - y) ** 2))
        if best is None or error < best[0]:
            best = (error, float(h), coefficients, predicted)
    if best is None:
        return None
    _, h, coefficients, predicted = best
    amplitude, offset = float(coefficients[0]), float(coefficients[1])
    body = f"abs({_shift(h)})"
    if abs(amplitude - 1.0) < 1e-9:
        expression = body
    elif abs(amplitude + 1.0) < 1e-9:
        expression = f"-{body}"
    else:
        expression = f"{_num(amplitude)}*{body}"
    if abs(offset) >= 1e-9:
        expression += f" {'+' if offset >= 0 else '-'} {_num(abs(offset))}"
    return {
        "key": "absolute",
        "method": "absolute_fit",
        "label": _MODEL_LABELS["absolute"],
        "expression": expression,
        "complexity": 4,
        "predicted": predicted,
    }


def _fit_rational(x: np.ndarray, y: np.ndarray) -> dict | None:
    span = max(float(np.max(x) - np.min(x)), 1e-6)
    candidates = list(np.linspace(float(np.min(x)) - 2.0 * span, float(np.min(x)) - 0.02 * span, 30))
    candidates += list(np.linspace(float(np.max(x)) + 0.02 * span, float(np.max(x)) + 2.0 * span, 30))
    best = None
    for b in candidates:
        denominator = x - b
        if np.min(np.abs(denominator)) < 1e-9:
            continue
        z = 1.0 / denominator
        a = np.column_stack([z, np.ones_like(z)])
        coefficients = _safe_lstsq(a, y)
        if coefficients is None:
            continue
        predicted = a @ coefficients
        error = float(np.sum((predicted - y) ** 2))
        if best is None or error < best[0]:
            best = (error, float(b), coefficients, predicted)
    if best is None:
        return None
    _, b, coefficients, predicted = best
    amplitude, offset = float(coefficients[0]), float(coefficients[1])
    body = f"1 / {_shift(b)}"
    if abs(amplitude - 1.0) < 1e-9:
        expression = body
    elif abs(amplitude + 1.0) < 1e-9:
        expression = f"-{body}"
    else:
        expression = f"{_num(amplitude)} * {body}"
    if abs(offset) >= 1e-9:
        expression += f" {'+' if offset >= 0 else '-'} {_num(abs(offset))}"
    return {
        "key": "rational",
        "method": "rational_fit",
        "label": _MODEL_LABELS["rational"],
        "expression": expression,
        "complexity": 4,
        "predicted": predicted,
    }


def _fit_trigonometric(x: np.ndarray, y: np.ndarray) -> dict | None:
    span = max(float(np.max(x) - np.min(x)), 1e-6)
    center = float((np.min(x) + np.max(x)) / 2.0)
    b_min = 2.0 * math.pi * 0.10 / span
    b_max = 2.0 * math.pi * 20.0 / span
    best = None
    for b in np.linspace(b_min, b_max, 360):
        z = x - center
        a = np.column_stack([np.sin(b * z), np.cos(b * z), np.ones_like(z)])
        coefficients = _safe_lstsq(a, y)
        if coefficients is None:
            continue
        predicted = a @ coefficients
        error = float(np.sum((predicted - y) ** 2))
        if best is None or error < best[0]:
            best = (error, float(b), coefficients, predicted)

    if best is None:
        return None
    # Local refinement around the best frequency.
    _, best_b, _, _ = best
    step = (b_max - b_min) / 360.0
    for b in np.linspace(max(b_min, best_b - 2 * step), min(b_max, best_b + 2 * step), 41):
        z = x - center
        a = np.column_stack([np.sin(b * z), np.cos(b * z), np.ones_like(z)])
        coefficients = _safe_lstsq(a, y)
        if coefficients is None:
            continue
        predicted = a @ coefficients
        error = float(np.sum((predicted - y) ** 2))
        if error < best[0]:
            best = (error, float(b), coefficients, predicted)

    _, b, coefficients, predicted = best
    sine, cosine, offset = (float(value) for value in coefficients)
    amplitude = math.hypot(sine, cosine)
    phase = math.atan2(cosine, sine)
    factor = _linear_factor(b, center)
    angle = factor
    if abs(phase) >= 1e-9:
        angle = f"{factor} {'+' if phase >= 0 else '-'} {_num(abs(phase))}"
    body = f"sin({angle})"
    if abs(amplitude - 1.0) < 1e-9:
        expression = body
    elif abs(amplitude) < 1e-10:
        expression = _num(offset)
    else:
        expression = f"{_num(amplitude)}*{body}"
    if abs(offset) >= 1e-9:
        expression += f" {'+' if offset >= 0 else '-'} {_num(abs(offset))}"
    return {
        "key": "trigonometric",
        "method": "trigonometric_fit",
        "label": _MODEL_LABELS["trigonometric"],
        "expression": expression,
        "complexity": 5,
        "predicted": predicted,
    }


def _fit_logistic(x: np.ndarray, y: np.ndarray) -> dict | None:
    span = max(float(np.max(x) - np.min(x)), 1e-6)
    min_x, max_x = float(np.min(x)), float(np.max(x))
    x0_values = np.linspace(min_x + 0.05 * span, max_x - 0.05 * span, 15)
    k_values = np.array([0.5, 1.0, 2.0, 4.0, 8.0, 16.0]) / span
    best = None
    for x0 in x0_values:
        for k in k_values:
            exponent = np.clip(-k * (x - x0), -500.0, 500.0)
            z = 1.0 / (1.0 + np.exp(exponent))
            a = np.column_stack([z, np.ones_like(z)])
            coefficients = _safe_lstsq(a, y)
            if coefficients is None:
                continue
            predicted = a @ coefficients
            error = float(np.sum((predicted - y) ** 2))
            if best is None or error < best[0]:
                best = (error, float(k), float(x0), coefficients, predicted)
    if best is None:
        return None
    _, k, x0, coefficients, predicted = best
    plateau, offset = float(coefficients[0]), float(coefficients[1])
    body = f"1 / (1 + exp({_linear_factor(-k, x0)}))"
    if abs(plateau - 1.0) < 1e-9:
        expression = body
    else:
        expression = f"{_num(plateau)} * {body}"
    if abs(offset) >= 1e-9:
        expression += f" {'+' if offset >= 0 else '-'} {_num(abs(offset))}"
    return {
        "key": "logistic",
        "method": "logistic_fit",
        "label": _MODEL_LABELS["logistic"],
        "expression": expression,
        "complexity": 5,
        "predicted": predicted,
    }


def _fit_by_key(key: str, x: np.ndarray, y: np.ndarray) -> dict | None:
    if key == "constant":
        return _fit_constant(x, y)
    if key.startswith("poly_"):
        return _polynomial_fit(x, y, int(key.split("_")[1]))
    return {
        "exponential": _fit_exponential,
        "logarithmic": _fit_logarithmic,
        "radical": _fit_radical,
        "absolute": _fit_absolute,
        "rational": _fit_rational,
        "trigonometric": _fit_trigonometric,
        "logistic": _fit_logistic,
    }[key](x, y)


def _prepare_points(points: Sequence[dict]) -> tuple[np.ndarray, np.ndarray, dict]:
    validation = validate_drawing(points)
    if validation["status"] != "valid":
        return np.array([]), np.array([]), validation

    ordered = sorted(
        ({"x": float(p["x"]), "y": float(p["y"])} for p in points),
        key=lambda p: p["x"],
    )
    x_span = max(ordered[-1]["x"] - ordered[0]["x"], 1e-9)
    tolerance = x_span * 1e-6

    groups: list[list[dict]] = []
    for point in ordered:
        if groups and abs(point["x"] - groups[-1][-1]["x"]) <= tolerance:
            groups[-1].append(point)
        else:
            groups.append([point])

    x_values = [float(np.mean([p["x"] for p in group])) for group in groups]
    y_values = [float(np.median([p["y"] for p in group])) for group in groups]

    if len(x_values) > MAX_RECOGNITION_POINTS:
        step = math.ceil(len(x_values) / MAX_RECOGNITION_POINTS)
        indices = list(range(0, len(x_values), step))
        if indices[-1] != len(x_values) - 1:
            indices.append(len(x_values) - 1)
        x_values = [x_values[i] for i in indices]
        y_values = [y_values[i] for i in indices]

    return np.asarray(x_values, dtype=float), np.asarray(y_values, dtype=float), validation


def _finite_expression(expression: str, x: np.ndarray) -> bool:
    try:
        compiled = compile_expression(expression)
        for value in x:
            if not math.isfinite(compiled.evaluate(float(value))):
                return False
    except ExpressionError:
        return False
    return True


def recognize_function(points: Sequence[dict]) -> dict:
    x, y, validation = _prepare_points(points)
    if validation["status"] != "valid":
        return {
            "status": "invalid" if validation["status"] == "invalid" else "uncertain",
            "is_function": False,
            "recognized": False,
            "expression": None,
            "method": None,
            "metrics": None,
            "domain": None,
            "confidence": None,
            "candidates": [],
            "warnings": [validation["message"]],
            "validation": validation,
        }

    if len(x) < 8:
        return {
            "status": "no_fit",
            "is_function": True,
            "recognized": False,
            "expression": None,
            "method": None,
            "metrics": None,
            "domain": None,
            "confidence": None,
            "candidates": [],
            "warnings": ["No hay suficientes puntos distintos para ajustar un modelo."],
            "validation": validation,
        }

    y_scale = max(float(np.max(y) - np.min(y)), 1e-9)
    raw_candidates: list[dict] = []

    constant = _fit_constant(x, y)
    if constant:
        raw_candidates.append(constant)
    for degree in range(1, 5):
        candidate = _polynomial_fit(x, y, degree)
        if candidate:
            raw_candidates.append(candidate)
    for fitter in (
        _fit_exponential,
        _fit_logarithmic,
        _fit_radical,
        _fit_absolute,
        _fit_rational,
        _fit_trigonometric,
        _fit_logistic,
    ):
        candidate = fitter(x, y)
        if candidate:
            raw_candidates.append(candidate)

    candidates: list[dict] = []
    seen_expressions: set[str] = set()
    for candidate in raw_candidates:
        expression = candidate["expression"]
        if expression in seen_expressions:
            continue
        if not _finite_expression(expression, x):
            continue
        seen_expressions.add(expression)
        metrics = _metrics(candidate["predicted"], y, y_scale)
        if not all(math.isfinite(value) for value in metrics.values()):
            continue
        score = metrics["relative_error"] + 0.005 * candidate["complexity"]
        candidates.append(
            {
                "expression": expression,
                "model": candidate["key"],
                "method": candidate["method"],
                "label": candidate["label"],
                "complexity": candidate["complexity"],
                "metrics": metrics,
                "score": score,
                "warnings": [],
            }
        )

    if not candidates:
        return {
            "status": "no_fit",
            "is_function": True,
            "recognized": False,
            "expression": None,
            "method": None,
            "metrics": None,
            "domain": {"start": float(np.min(x)), "end": float(np.max(x))},
            "confidence": None,
            "candidates": [],
            "warnings": ["No se encontró un modelo matemático suficientemente compatible."],
            "validation": validation,
        }

    candidates.sort(key=lambda item: item["score"])

    # Holdout validation for the strongest candidates.  The final expression is
    # still fitted on all points, but the reported validation_rmse uses a
    # deterministic holdout so it is not simply training error.
    if len(x) >= HOLDOUT_MIN_POINTS:
        holdout_mask = np.arange(len(x)) % 5 == 0
        if np.count_nonzero(~holdout_mask) >= 5 and np.count_nonzero(holdout_mask) >= 4:
            for candidate in candidates[:7]:
                train_x, train_y = x[~holdout_mask], y[~holdout_mask]
                test_x, test_y = x[holdout_mask], y[holdout_mask]
                holdout_fit = _fit_by_key(candidate["model"], train_x, train_y)
                if not holdout_fit:
                    continue
                try:
                    compiled = compile_expression(holdout_fit["expression"])
                    predicted = np.asarray(
                        [compiled.evaluate(float(value)) for value in test_x],
                        dtype=float,
                    )
                except ExpressionError:
                    continue
                holdout_metrics = _metrics(
                    predicted,
                    test_y,
                    max(float(np.max(train_y) - np.min(train_y)), 1e-9),
                )
                candidate["metrics"]["validation_rmse"] = holdout_metrics["rmse"]
                candidate["metrics"]["validation_relative_error"] = holdout_metrics[
                    "relative_error"
                ]
                holdout_penalty = 0.5 * holdout_metrics["relative_error"]
                candidate["score"] += holdout_penalty

    candidates.sort(key=lambda item: item["score"])

    domain = {"start": float(np.min(x)), "end": float(np.max(x))}
    for candidate in candidates:
        candidate["domain"] = domain
        candidate["warnings"] = []
        metrics = candidate["metrics"]
        if metrics["relative_error"] > 0.08:
            candidate["warnings"].append(
                "El error relativo es alto; la expresión es solo una aproximación."
            )
        if candidate.get("metrics", {}).get("validation_relative_error", 0) > 0.15:
            candidate["warnings"].append(
                "El error sobre puntos no usados en el ajuste es alto."
            )

    best = candidates[0]
    best_metrics = best["metrics"]
    holdout_relative = best_metrics.get("validation_relative_error")

    if best_metrics["relative_error"] <= 0.08 and (
        holdout_relative is None or holdout_relative <= 0.15
    ):
        status = "success"
        recognized = True
        confidence = (
            "alta"
            if best_metrics["relative_error"] <= 0.02
            and (holdout_relative is None or holdout_relative <= 0.05)
            else "media"
        )
    elif best_metrics["relative_error"] <= 0.20:
        status = "low_confidence"
        recognized = False
        confidence = "baja"
    else:
        status = "low_confidence"
        recognized = False
        confidence = "baja"

    warnings = [
        "La expresión es una aproximación obtenida de puntos finitos; no es una identidad matemática exacta.",
        "El intervalo se limita a los datos observados; no se extrapola fuera de él.",
    ]
    if status != "success":
        warnings.append(
            "La confianza es baja. Revisa o edita la expresión antes de usarla para calcular una integral."
        )
    if confidence == "media":
        warnings.append(
            "La confianza es una etiqueta heurística basada en el error, no una probabilidad calibrada."
        )

    def public_candidate(item: dict) -> dict:
        return {
            "expression": item["expression"],
            "model": item["model"],
            "method": item["method"],
            "label": item["label"],
            "complexity": item["complexity"],
            "metrics": item["metrics"],
            "domain": item["domain"],
            "warnings": item["warnings"],
        }

    return {
        "status": status,
        "is_function": True,
        "recognized": recognized,
        "expression": best["expression"],
        "method": best["method"],
        "metrics": best_metrics,
        "domain": domain,
        "confidence": confidence,
        "candidates": [public_candidate(item) for item in candidates[:MAX_CANDIDATES]],
        "warnings": warnings,
        "validation": validation,
    }
