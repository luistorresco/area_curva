"""Volumes of solids of revolution.

The module implements the three classical methods:

* ``discos``    V = π ∫ [R(t)]² dt
* ``arandelas`` V = π ∫ ([R(t)]² − [r(t)]²) dt
* ``capas``     V = 2π ∫ ρ(t) h(t) dt

The integration variable is selected from the method and the revolution
axis.  Revolving around the X axis and using discs/washers integrates in
``x``; revolving around the Y axis integrates in ``y``.  The shell method
integrates in the direction *perpendicular* to the revolution axis, so it
uses ``x`` around the Y axis and ``y`` around the X axis.

All expressions are parsed by :mod:`math_engine` with the same AST whitelist
used by the rest of the API.  Integrals are evaluated with the composite
Simpson rule, which is exact for polynomials up to degree three per panel and
gives good accuracy for smooth curves.
"""

from __future__ import annotations

import math

from math_engine import (
    ExpressionEvaluationError,
    compile_expression,
)

MIN_VOLUME_SAMPLES = 20
MAX_VOLUME_SAMPLES = 5000

METHOD_LABELS = {
    "discos": "Discos",
    "arandelas": "Arandelas",
    "capas": "Capas cilíndricas",
}

AXIS_LABELS = {
    "x": "eje X (y = 0)",
    "y": "eje Y (x = 0)",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt(value: float) -> str:
    """Compact number formatting for the explanatory steps."""

    if value == 0:
        return "0"
    if abs(value) >= 1e6 or abs(value) < 1e-4:
        return f"{value:.6g}"
    return f"{value:.6g}"


def _cartesian(t: float, value: float, variable: str) -> dict[str, float]:
    """Map an integration pair to Cartesian (x, y) coordinates."""

    if variable == "x":
        return {"x": float(t), "y": float(value)}
    return {"x": float(value), "y": float(t)}


def _evaluate(expression, t: float, variable: str) -> float:
    try:
        value = expression.evaluate(t)
    except ExpressionEvaluationError as exc:
        raise ExpressionEvaluationError(
            f"No se pudo evaluar la función en {variable} = {t:.6g}: {exc}", x=t
        ) from exc
    if not math.isfinite(value):
        raise ExpressionEvaluationError(
            f"La función produce un valor no finito en {variable} = {t:.6g}.", x=t
        )
    return float(value)


def _simpson(values: list[float], start: float, end: float) -> float:
    """Composite Simpson rule for an even number of panels."""

    panels = len(values) - 1
    if panels <= 0:
        return 0.0
    if panels % 2:
        # Defensive fallback: the public entry point always requests an even
        # number of panels, but a direct caller may pass an odd list.
        h = (end - start) / panels
        return sum(
            (values[i] + values[i + 1]) * 0.5 * h for i in range(panels)
        )
    h = (end - start) / panels
    total = values[0] + values[-1]
    total += 4.0 * sum(values[1:-1:2])
    total += 2.0 * sum(values[2:-1:2])
    return total * h / 3.0


def integration_variable(method: str, axis: str) -> str:
    """Return the variable that the chosen method/axis pair must integrate."""

    if method in ("discos", "arandelas"):
        return axis
    if method == "capas":
        return "y" if axis == "x" else "x"
    raise ValueError(f"Método desconocido: '{method}'.")


def _validate_settings(
    method: str, axis: str, start: float, end: float, samples: int
) -> tuple[str, int]:
    if method not in METHOD_LABELS:
        raise ValueError(
            "El método debe ser 'discos', 'arandelas' o 'capas'."
        )
    if axis not in ("x", "y"):
        raise ValueError("El eje de revolución debe ser 'x' o 'y'.")
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("Los límites del intervalo deben ser números finitos.")
    if start >= end:
        raise ValueError("El inicio del intervalo debe ser menor que el fin.")
    if end - start > 1e6:
        raise ValueError("El intervalo es demasiado amplio.")
    if not isinstance(samples, int) or not (
        MIN_VOLUME_SAMPLES <= samples <= MAX_VOLUME_SAMPLES
    ):
        raise ValueError(
            f"El número de muestras debe estar entre {MIN_VOLUME_SAMPLES} y "
            f"{MAX_VOLUME_SAMPLES}."
        )

    # Simpson needs an even number of panels.  Adjusting by one sample keeps
    # the user's requested resolution and avoids a silent loss of precision.
    if samples % 2:
        samples = min(samples + 1, MAX_VOLUME_SAMPLES)

    return integration_variable(method, axis), samples


def _display_points(
    ts: list[float],
    values: list[float],
    variable: str,
    target: int = 240,
) -> list[dict[str, float]]:
    if not ts:
        return []
    step = max(1, len(ts) // target)
    indices = list(range(0, len(ts), step))
    if indices[-1] != len(ts) - 1:
        indices.append(len(ts) - 1)
    return [_cartesian(ts[i], values[i], variable) for i in indices]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def volume_solid(
    method: str,
    axis: str,
    f_expression: str,
    g_expression: str,
    start: float,
    end: float,
    samples: int = 2000,
) -> dict:
    """Compute the volume of a solid of revolution and explain each step."""

    variable, samples = _validate_settings(method, axis, start, end, samples)

    f = compile_expression(f_expression, variable=variable)
    needs_inner = method in ("arandelas", "capas")
    g_source = (g_expression or "0").strip() or "0"
    g = compile_expression(g_source, variable=variable) if needs_inner else None

    h = (end - start) / samples
    ts = [start + h * i for i in range(samples + 1)]
    f_values = [_evaluate(f, t, variable) for t in ts]
    g_values = (
        [_evaluate(g, t, variable) for t in ts]
        if g is not None
        else [0.0 for _ in ts]
    )

    warnings: list[str] = []
    integrand: list[float] = []

    if method == "discos":
        for t, fv in zip(ts, f_values):
            if fv < -1e-12:
                warnings.append(
                    "La función toma valores negativos; el radio se usa como |f| "
                    "y el volumen no cambia."
                )
                break
        integrand = [fv * fv for fv in f_values]
        factor = math.pi
        formula = f"V = π ∫ [R({variable})]² d{variable}"
        setup = (
            f"V = π ∫[{_fmt(start)}, {_fmt(end)}] "
            f"[{f_expression}]² d{variable}"
        )
    elif method == "arandelas":
        # A washer is only meaningful when both curves stay on the same side
        # of the axis; otherwise the region crosses the axis and the solid is
        # not an annulus.
        for t, fv, gv in zip(ts, f_values, g_values):
            if fv * gv < -1e-18:
                raise ValueError(
                    "La región cruza el eje de giro. Para usar arandelas, las dos "
                    f"curvas deben estar del mismo lado del eje; en {variable} = "
                    f"{t:.6g} se obtuvo f = {fv:.6g} y g = {gv:.6g}."
                )
            if abs(fv) + 1e-9 < abs(gv):
                raise ValueError(
                    "El radio exterior R debe ser mayor o igual que el radio "
                    f"interior r. En {variable} = {t:.6g} se obtuvo "
                    f"R = {abs(fv):.6g} y r = {abs(gv):.6g}."
                )
        integrand = [
            abs(fv) * abs(fv) - abs(gv) * abs(gv)
            for fv, gv in zip(f_values, g_values)
        ]
        factor = math.pi
        formula = f"V = π ∫ ([R({variable})]² − [r({variable})]²) d{variable}"
        setup = (
            f"V = π ∫[{_fmt(start)}, {_fmt(end)}] "
            f"([{f_expression}]² − [{g_source}]²) d{variable}"
        )
    else:  # capas
        if start < -1e-12:
            raise ValueError(
                "Para el método de capas el intervalo debe estar en el lado "
                f"positivo del eje de giro ({variable} ≥ 0)."
            )
        for t, fv, gv in zip(ts, f_values, g_values):
            if fv - gv < -1e-9:
                raise ValueError(
                    "La curva exterior (f) debe quedar por encima o a la derecha "
                    f"de la interior (g). En {variable} = {t:.6g} se obtuvo "
                    f"f = {fv:.6g} y g = {gv:.6g}."
                )
        integrand = [
            max(t, 0.0) * max(fv - gv, 0.0)
            for t, fv, gv in zip(ts, f_values, g_values)
        ]
        factor = 2.0 * math.pi
        formula = f"V = 2π ∫ ρ({variable}) h({variable}) d{variable}"
        setup = (
            f"V = 2π ∫[{_fmt(start)}, {_fmt(end)}] "
            f"{variable}·([{f_expression}] − [{g_source}]) d{variable}"
        )

    integral = _simpson(integrand, start, end)
    volume = factor * integral
    if not math.isfinite(volume):
        raise ValueError("El volumen calculado no es un número finito.")
    # Tiny negative values can appear from floating-point cancellation.
    if volume < 0 and abs(volume) < 1e-12:
        volume = 0.0
    if volume < 0:
        raise ValueError(
            "El volumen calculado es negativo. Revisa el orden de las curvas y "
            "el eje de giro."
        )

    if samples < 200:
        warnings.append(
            "El muestreo es bajo; aumenta las muestras para mejorar la precisión."
        )

    f_points = _display_points(ts, f_values, variable)
    g_points = (
        _display_points(ts, g_values, variable)
        if method in ("arandelas", "capas")
        else []
    )

    steps = _build_steps(
        method=method,
        axis=axis,
        variable=variable,
        f_expression=f_expression,
        g_expression=g_source,
        start=start,
        end=end,
        samples=samples,
        panel_width=h,
        formula=formula,
        setup=setup,
        volume=volume,
    )

    return {
        "method": method,
        "axis": axis,
        "variable": variable,
        "start": start,
        "end": end,
        "volume": volume,
        "integral": integral,
        "factor": factor,
        "samples_used": samples,
        "evaluations": (samples + 1) * (2 if method in ("arandelas", "capas") else 1),
        "method_label": METHOD_LABELS[method],
        "axis_label": AXIS_LABELS[axis],
        "formula": formula,
        "setup": setup,
        "steps": steps,
        "f_points": f_points,
        "g_points": g_points,
        "warnings": warnings,
        "has_valid_result": True,
    }


# ---------------------------------------------------------------------------
# Volumes from an imported profile (stroke or plotted function)
# ---------------------------------------------------------------------------


def _prepare_profile(points: list[dict]) -> tuple[list[float], list[float]]:
    """Return a clean, x-sorted polyline for the imported curve."""

    pairs: list[tuple[float, float]] = []
    for point in points:
        try:
            x = float(point["x"])
            y = float(point["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            pairs.append((x, y))

    if len(pairs) < 2:
        raise ValueError("El trazo debe tener al menos dos puntos finitos.")
    pairs.sort(key=lambda pair: pair[0])

    xs: list[float] = []
    ys: list[float] = []
    for x, y in pairs:
        if xs and abs(x - xs[-1]) <= 1e-12:
            # Duplicate x values are averaged so the stroke is usable as f(x).
            ys[-1] = 0.5 * (ys[-1] + y)
        else:
            xs.append(x)
            ys.append(y)

    if len(xs) < 2 or xs[-1] - xs[0] <= 1e-12:
        raise ValueError("El trazo no tiene un intervalo horizontal válido.")
    return xs, ys


def _profile_value(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation of the imported curve at x."""

    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    low, high = 0, len(xs) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if xs[middle] <= x:
            low = middle
        else:
            high = middle
    span = xs[high] - xs[low]
    if span <= 0:
        return ys[low]
    ratio = (x - xs[low]) / span
    return ys[low] + (ys[high] - ys[low]) * ratio


def _boundary_t(a0: float, a1: float, y: float) -> float | None:
    """Fraction where a segment crosses the horizontal level y."""

    denominator = a1 - a0
    if abs(denominator) < 1e-15:
        return None
    t = (y - a0) / denominator
    if -1e-9 <= t <= 1.0 + 1e-9:
        return min(max(t, 0.0), 1.0)
    return None


def _segment_boundary(
    x0: float,
    x1: float,
    lo0: float,
    lo1: float,
    hi0: float,
    hi1: float,
    y: float,
    entering: bool,
) -> float:
    """Approximate where the region enters or leaves a horizontal slice."""

    candidates: list[float] = []
    t = _boundary_t(lo0, lo1, y)
    if t is not None:
        candidates.append(t)
    t = _boundary_t(hi0, hi1, y)
    if t is not None:
        candidates.append(t)
    if not candidates:
        return x0 if entering else x1
    t = min(candidates) if entering else max(candidates)
    return x0 + (x1 - x0) * t


def _intervals_at_y(
    x_grid: list[float],
    lo_values: list[float],
    hi_values: list[float],
    y: float,
) -> list[tuple[float, float]]:
    """Horizontal intervals of the region at height y."""

    tolerance = 1e-12
    intervals: list[tuple[float, float]] = []
    inside = False
    start = 0.0

    for index, x in enumerate(x_grid):
        contains = lo_values[index] <= y + tolerance and y <= hi_values[index] + tolerance
        if contains and not inside:
            if index == 0:
                start = x
            else:
                start = _segment_boundary(
                    x_grid[index - 1],
                    x_grid[index],
                    lo_values[index - 1],
                    lo_values[index],
                    hi_values[index - 1],
                    hi_values[index],
                    y,
                    True,
                )
            inside = True
        elif not contains and inside:
            end = _segment_boundary(
                x_grid[index - 1],
                x_grid[index],
                lo_values[index - 1],
                lo_values[index],
                hi_values[index - 1],
                hi_values[index],
                y,
                False,
            )
            if end > start + 1e-12:
                intervals.append((start, end))
            inside = False

    if inside and x_grid[-1] > start + 1e-12:
        intervals.append((start, x_grid[-1]))
    return intervals


def _cross_section_grid(
    xs: list[float],
    ys: list[float],
    g,
    grid_size: int,
) -> tuple[list[float], list[float], list[float]]:
    """Precompute the vertical interval between f(x) and g(x)."""

    x_min, x_max = xs[0], xs[-1]
    grid_size = max(2, grid_size)
    x_grid = [
        x_min + (x_max - x_min) * index / (grid_size - 1)
        for index in range(grid_size)
    ]
    f_values = [_profile_value(xs, ys, x) for x in x_grid]
    g_values = (
        [_evaluate(g, x, "x") for x in x_grid]
        if g is not None
        else [0.0 for _ in x_grid]
    )
    lo_values = [min(fv, gv) for fv, gv in zip(f_values, g_values)]
    hi_values = [max(fv, gv) for fv, gv in zip(f_values, g_values)]
    return x_grid, lo_values, hi_values


def _slice_radii(intervals: list[tuple[float, float]]) -> tuple[float, float]:
    """Return the outer and inner distances of a horizontal slice to x = 0."""

    if not intervals:
        return 0.0, 0.0

    endpoints = [value for interval in intervals for value in interval]
    outer = max(abs(value) for value in endpoints)
    touched_axis = any(start <= 1e-9 and end >= -1e-9 for start, end in intervals)
    inner = 0.0 if touched_axis else min(abs(value) for value in endpoints)
    if outer < inner:
        outer, inner = inner, outer
    return outer, inner


def _one_sided_endpoints(values: list[float]) -> None:
    """Use the one-sided limit at a slice boundary.

    At the top or bottom of the region the horizontal slice can collapse to a
    point.  That single sample has zero measure, but Simpson's rule still uses
    it; taking the neighbouring value removes an artificial endpoint bias.
    """

    if len(values) < 3:
        return
    if values[0] == 0.0 and values[1] != 0.0:
        values[0] = values[1]
    if values[-1] == 0.0 and values[-2] != 0.0:
        values[-1] = values[-2]


def _profile_display_points(
    xs: list[float], ys: list[float], target: int = 240
) -> list[dict[str, float]]:
    if not xs:
        return []
    step = max(1, len(xs) // target)
    indices = list(range(0, len(xs), step))
    if indices[-1] != len(xs) - 1:
        indices.append(len(xs) - 1)
    return [{"x": xs[index], "y": ys[index]} for index in indices]


def volume_from_profile(
    method: str,
    axis: str,
    points: list[dict],
    g_expression: str = "0",
    start: float | None = None,
    end: float | None = None,
    samples: int = 2000,
    f_expression: str | None = None,
    source: str | None = None,
) -> dict:
    """Compute a volume directly from an imported stroke/function.

    The imported curve is the boundary ``f(x)`` of the region.  The chosen
    method and axis decide which cuts are taken; the radii/heights are read
    from the actual curve instead of swapping ``x`` and ``y`` in an
    expression.  This keeps the user's stroke valid when the method or the
    revolution axis changes.
    """

    if method not in METHOD_LABELS:
        raise ValueError("El método debe ser 'discos', 'arandelas' o 'capas'.")
    if axis not in ("x", "y"):
        raise ValueError("El eje de revolución debe ser 'x' o 'y'.")
    if not isinstance(samples, int) or not (
        MIN_VOLUME_SAMPLES <= samples <= MAX_VOLUME_SAMPLES
    ):
        raise ValueError(
            f"El número de muestras debe estar entre {MIN_VOLUME_SAMPLES} y "
            f"{MAX_VOLUME_SAMPLES}."
        )
    if samples % 2:
        samples = min(samples + 1, MAX_VOLUME_SAMPLES)

    xs, ys = _prepare_profile(points)
    x_min, x_max = xs[0], xs[-1]
    g_source = (g_expression or "0").strip() or "0"
    needs_inner = method in ("arandelas", "capas")
    g = compile_expression(g_source, variable="x") if needs_inner else None
    variable = integration_variable(method, axis)

    warnings: list[str] = []
    if (
        method == "arandelas"
        and variable == "x"
        and g_source.replace(" ", "") in ("0", "0.0", "0.00")
    ):
        warnings.append(
            "Con g(x) = 0 el radio interior es 0; las arandelas coinciden con "
            "los discos. Con una sola curva no se forma un hueco."
        )
    profile_points = _profile_display_points(xs, ys)
    f_label = (f_expression or "trazo dibujado").strip() or "trazo dibujado"

    if variable == "x":
        if method == "capas":
            # Shells around Y must use radii x >= 0.  A curve entirely on the
            # negative side is reflected to the positive side: it generates
            # the same solid when revolved around Y.
            if x_max <= 0:
                natural_start, natural_end = 0.0, -x_min
                mirror = True
                warnings.append(
                    "El trazo está en x ≤ 0; se reflejó al lado positivo para "
                    "girar alrededor del eje Y."
                )
            else:
                natural_start, natural_end = max(0.0, x_min), x_max
                mirror = False
                if x_min < -1e-9:
                    warnings.append(
                        "Se usó la parte x ≥ 0 del trazo; la parte negativa "
                        "genera el mismo sólido al girar alrededor del eje Y."
                    )

            used_start = natural_start if start is None else start
            used_end = natural_end if end is None else end
            if (
                used_start < natural_start - 1e-9
                or used_end > natural_end + 1e-9
                or used_start >= used_end
            ):
                raise ValueError(
                    "El intervalo del trazo debe estar dentro de "
                    f"[{_fmt(natural_start)}, {_fmt(natural_end)}] para las capas "
                    "alrededor del eje Y."
                )

            h = (used_end - used_start) / samples
            ts = [used_start + h * index for index in range(samples + 1)]
            eval_xs = [-t for t in ts] if mirror else ts
            f_values = [_profile_value(xs, ys, x) for x in eval_xs]
            g_values = (
                [_evaluate(g, x, "x") for x in eval_xs]
                if g is not None
                else [0.0 for _ in ts]
            )
            heights = [abs(fv - gv) for fv, gv in zip(f_values, g_values)]
            integrand = [t * height for t, height in zip(ts, heights)]
            factor = 2.0 * math.pi
            formula = "V = 2π ∫ ρ(x) h(x) dx"
            setup = (
                f"V = 2π ∫[{_fmt(used_start)}, {_fmt(used_end)}] "
                "x · |f(x) − g(x)| dx"
            )
            f_display = f_values
            g_display = g_values
        else:
            used_start = x_min if start is None else start
            used_end = x_max if end is None else end
            if (
                used_start < x_min - 1e-9
                or used_end > x_max + 1e-9
                or used_start >= used_end
            ):
                raise ValueError(
                    "El intervalo del trazo debe estar dentro de "
                    f"[{_fmt(x_min)}, {_fmt(x_max)}]."
                )

            h = (used_end - used_start) / samples
            ts = [used_start + h * index for index in range(samples + 1)]
            f_values = [_profile_value(xs, ys, x) for x in ts]
            g_values = (
                [_evaluate(g, x, "x") for x in ts]
                if g is not None
                else [0.0 for _ in ts]
            )

            if method == "discos":
                if any(value < -1e-12 for value in f_values):
                    warnings.append(
                        "La curva toma valores negativos; el radio se usa como "
                        "|f(x)| y el volumen no cambia."
                    )
                integrand = [value * value for value in f_values]
                factor = math.pi
                formula = "V = π ∫ [R(x)]² dx"
                setup = (
                    f"V = π ∫[{_fmt(used_start)}, {_fmt(used_end)}] "
                    "[f(x)]² dx"
                )
                f_display = f_values
                g_display = []
            else:
                outer_values: list[float] = []
                inner_values: list[float] = []
                crossed_axis = False
                for fv, gv in zip(f_values, g_values):
                    outer_values.append(max(abs(fv), abs(gv)))
                    if fv * gv < -1e-18:
                        # The vertical slice crosses the axis: the washer
                        # collapses to a disc at that cut.
                        inner_values.append(0.0)
                        crossed_axis = True
                    else:
                        inner_values.append(min(abs(fv), abs(gv)))
                if crossed_axis:
                    warnings.append(
                        "La región cruza el eje X; en los cortes que lo cruzan "
                        "la arandela se convierte en un disco (r = 0)."
                    )
                integrand = [
                    outer * outer - inner * inner
                    for outer, inner in zip(outer_values, inner_values)
                ]
                factor = math.pi
                formula = "V = π ∫ ([R(x)]² − [r(x)]²) dx"
                setup = (
                    f"V = π ∫[{_fmt(used_start)}, {_fmt(used_end)}] "
                    "([R(x)]² − [r(x)]²) dx"
                )
                f_display = outer_values
                g_display = inner_values
    else:
        # Methods that integrate in y need the horizontal cross-sections of
        # the region at every height.
        grid_size = max(500, min(1600, samples))
        x_grid, lo_values, hi_values = _cross_section_grid(
            xs, ys, g, grid_size
        )
        y_min = min(lo_values)
        y_max = max(hi_values)
        if y_max - y_min <= 1e-12:
            raise ValueError("La región del trazo no tiene altura suficiente.")

        cache: dict[float, list[tuple[float, float]]] = {}

        def intervals_for(height: float) -> list[tuple[float, float]]:
            key = round(height, 12)
            if key not in cache:
                cache[key] = _intervals_at_y(
                    x_grid, lo_values, hi_values, height
                )
            return cache[key]

        if method == "capas":
            radius_max = max(abs(y_min), abs(y_max))
            used_start = 0.0 if start is None else max(0.0, start)
            used_end = radius_max if end is None else end
            if used_start >= used_end or used_end > radius_max + 1e-9:
                raise ValueError(
                    "El intervalo radial de las capas alrededor del eje X debe "
                    f"estar dentro de [0, {_fmt(radius_max)}]."
                )
            h = (used_end - used_start) / samples
            ts = [used_start + h * index for index in range(samples + 1)]
            heights: list[float] = []
            for t in ts:
                positive = (
                    sum(end - begin for begin, end in intervals_for(t))
                    if y_min <= t <= y_max
                    else 0.0
                )
                negative = (
                    sum(end - begin for begin, end in intervals_for(-t))
                    if y_min <= -t <= y_max
                    else 0.0
                )
                heights.append(positive + negative)
            _one_sided_endpoints(heights)
            integrand = [t * height for t, height in zip(ts, heights)]
            factor = 2.0 * math.pi
            formula = "V = 2π ∫ ρ(y) h(y) dy"
            setup = (
                f"V = 2π ∫[{_fmt(used_start)}, {_fmt(used_end)}] "
                "y · h(y) dy"
            )
            f_display = heights
            g_display = [0.0 for _ in ts]

            if y_min < -1e-9 and y_max > 1e-9:
                warnings.append(
                    "La región cruza el eje X; se combinaron las alturas de "
                    "ambos lados para cada radio."
                )
            elif y_max <= 0:
                warnings.append(
                    "La región está por debajo del eje X; se usó el radio |y|."
                )
        else:
            used_start = y_min if start is None else start
            used_end = y_max if end is None else end
            if used_start < y_min - 1e-9 or used_end > y_max + 1e-9:
                raise ValueError(
                    "El intervalo del trazo debe estar dentro de "
                    f"[{_fmt(y_min)}, {_fmt(y_max)}]."
                )
            if used_start >= used_end:
                raise ValueError("El inicio del intervalo debe ser menor que el fin.")

            h = (used_end - used_start) / samples
            ts = [used_start + h * index for index in range(samples + 1)]
            outer_values = []
            inner_values = []
            multiple_slices = False
            for t in ts:
                intervals = intervals_for(t)
                if len(intervals) > 1:
                    multiple_slices = True
                outer, inner = _slice_radii(intervals)
                outer_values.append(outer)
                inner_values.append(inner)

            _one_sided_endpoints(outer_values)
            _one_sided_endpoints(inner_values)

            if method == "discos":
                integrand = [outer * outer for outer in outer_values]
                factor = math.pi
                formula = "V = π ∫ [R(y)]² dy"
                setup = (
                    f"V = π ∫[{_fmt(used_start)}, {_fmt(used_end)}] "
                    "[R(y)]² dy"
                )
                f_display = outer_values
                g_display = []
                if any(inner > 1e-9 for inner in inner_values):
                    warnings.append(
                        "La región no toca el eje Y en todo el intervalo; el "
                        "método de discos ignora el hueco interior. Usa "
                        "arandelas para incluirlo."
                    )
            else:
                integrand = [
                    outer * outer - inner * inner
                    for outer, inner in zip(outer_values, inner_values)
                ]
                factor = math.pi
                formula = "V = π ∫ ([R(y)]² − [r(y)]²) dy"
                setup = (
                    f"V = π ∫[{_fmt(used_start)}, {_fmt(used_end)}] "
                    "([R(y)]² − [r(y)]²) dy"
                )
                f_display = outer_values
                g_display = inner_values

            if multiple_slices:
                warnings.append(
                    "La región tiene varios tramos horizontales en algunos "
                    "cortes; se usó el radio exterior máximo y el interior "
                    "mínimo."
                )

    integral = _simpson(integrand, used_start, used_end)
    volume = factor * integral
    if not math.isfinite(volume):
        raise ValueError("El volumen calculado no es un número finito.")
    if volume < 0 and abs(volume) < 1e-12:
        volume = 0.0
    if volume < 0:
        raise ValueError(
            "El volumen calculado es negativo. Revisa el método y el eje."
        )

    if samples < 200:
        warnings.append(
            "El muestreo es bajo; aumenta las muestras para mejorar la precisión."
        )

    f_points = _display_points(ts, f_display, variable)
    g_points = (
        _display_points(ts, g_display, variable) if g_display else []
    )

    steps = _build_profile_steps(
        method=method,
        axis=axis,
        variable=variable,
        start=used_start,
        end=used_end,
        samples=samples,
        panel_width=h,
        formula=formula,
        setup=setup,
        volume=volume,
        f_expression=f_label,
        g_expression=g_source if needs_inner else "0",
        source=source,
    )

    return {
        "method": method,
        "axis": axis,
        "variable": variable,
        "start": used_start,
        "end": used_end,
        "volume": volume,
        "integral": integral,
        "factor": factor,
        "samples_used": samples,
        "evaluations": (samples + 1)
        * (2 if needs_inner else 1)
        + (len(x_grid) if variable == "y" else 0),
        "method_label": METHOD_LABELS[method],
        "axis_label": AXIS_LABELS[axis],
        "formula": formula,
        "setup": setup,
        "steps": steps,
        "f_points": f_points,
        "g_points": g_points,
        "warnings": warnings,
        "has_valid_result": True,
        "profile": True,
        "profile_points": profile_points,
        "f_expression": f_label,
        "g_expression": g_source if needs_inner else "0",
    }


def _build_profile_steps(
    *,
    method: str,
    axis: str,
    variable: str,
    start: float,
    end: float,
    samples: int,
    panel_width: float,
    formula: str,
    setup: str,
    volume: float,
    f_expression: str,
    g_expression: str,
    source: str | None,
) -> list[dict]:
    """Explain a profile-based volume calculation."""

    axis_label = AXIS_LABELS[axis]
    a, b = _fmt(start), _fmt(end)
    source_text = (
        "la función escrita arriba"
        if (source or "").lower() in ("function", "funcion", "función")
        else "el trazo dibujado arriba"
    )
    has_expression = bool(f_expression) and f_expression not in (
        "trazo del usuario",
        "trazo dibujado",
    )
    if has_expression:
        curve_text = f"La curva es f(x) = {f_expression}."
        curve_formula = f"f(x) = {f_expression}"
    else:
        curve_text = "La curva es el trazo dibujado por el usuario."
        curve_formula = "f(x): trazo dibujado"
    steps: list[dict] = [
        {
            "title": "Curva y región",
            "text": (
                f"Se toma {source_text} como frontera de la región. "
                f"{curve_text} Se gira alrededor del {axis_label}; "
                f"el método integra respecto a {variable} entre {a} y {b}. "
                "El cálculo usa los puntos reales de la curva, no una "
                "expresión reescrita en otra variable."
            ),
            "formula": curve_formula,
        }
    ]

    if method == "discos":
        if variable == "x":
            element = (
                "Cada corte perpendicular al eje X es un disco de radio "
                "R(x) = |f(x)|."
            )
            element_formula = "R(x) = |f(x)|"
        else:
            element = (
                "Cada corte perpendicular al eje Y es un disco de radio R(y), "
                "la distancia máxima del trazo al eje Y en esa altura."
            )
            element_formula = "R(y) = max |x| del trazo en el corte"
        steps.append(
            {
                "title": "Elemento del método de discos",
                "text": (
                    f"{element} El área del disco es πR² y al integrarla a lo "
                    "largo del eje se obtiene el volumen."
                ),
                "formula": element_formula,
            }
        )
    elif method == "arandelas":
        if variable == "x":
            element = (
                "Cada corte perpendicular al eje X es una arandela. R(x) es "
                "la distancia exterior y r(x) la interior entre las curvas "
                "f(x) y g(x)."
            )
            element_formula = (
                f"R(x) = max(|f(x)|, |g(x)|),  r(x) = min(|f(x)|, |g(x)|)"
            )
        else:
            element = (
                "Cada corte perpendicular al eje Y es una arandela. R(y) es "
                "la distancia máxima del trazo al eje y r(y) la mínima; si el "
                "trazo toca el eje, r(y) = 0."
            )
            element_formula = "R(y) = max |x|,  r(y) = min |x| en el corte"
        steps.append(
            {
                "title": "Elemento del método de arandelas",
                "text": (
                    f"{element} El área es π(R² − r²), que al integrarse "
                    "acumula el volumen del sólido con hueco."
                ),
                "formula": element_formula,
            }
        )
    else:
        if axis == "y":
            element = (
                "Cada capa es un cilindro de radio ρ(x) = x y altura h(x), "
                "la distancia vertical entre las curvas f(x) y g(x)."
            )
            element_formula = "ρ(x) = x,  h(x) = |f(x) − g(x)|"
        else:
            element = (
                "Cada capa es un cilindro de radio ρ(y) = |y| y altura h(y), "
                "el ancho horizontal total del trazo en esa altura."
            )
            element_formula = "ρ(y) = |y|,  h(y) = ancho horizontal del trazo"
        steps.append(
            {
                "title": "Elemento del método de capas",
                "text": (
                    f"{element} El volumen de una capa es 2πρh d{variable}; "
                    "al integrar se suman todas las capas concéntricas."
                ),
                "formula": element_formula,
            }
        )

    steps.append(
        {
            "title": "Integral planteada",
            "text": (
                "Los radios o la altura se obtienen del trazo en cada corte. "
                "Al cambiar el método o el eje, la misma curva se proyecta de "
                "otra forma y el sólido puede cambiar."
            ),
            "formula": setup,
        }
    )
    steps.append(
        {
            "title": "Integración numérica",
            "text": (
                f"Se aplica la regla de Simpson compuesta con n = {samples} "
                f"subintervalos de ancho h = {_fmt(panel_width)}. Simpson "
                "combina evaluaciones con pesos 1, 4, 2, 4, …, 1."
            ),
            "formula": "V ≈ factor · (h/3) · [w₀·I₀ + w₁·I₁ + … + wₙ·Iₙ]",
        }
    )
    steps.append(
        {
            "title": "Resultado",
            "text": (
                f"El volumen del sólido es aproximadamente {_fmt(volume)} "
                "unidades cúbicas."
            ),
            "formula": f"V ≈ {_fmt(volume)} u³",
        }
    )
    steps.append(
        {
            "title": "Interpretación",
            "text": (
                "El mismo trazo puede generar sólidos distintos según el eje "
                "y el método. Si dos métodos describen el mismo sólido, sus "
                "volúmenes deben coincidir; si cambias el eje, cambia la "
                "distancia de cada punto al giro y cambia el volumen."
            ),
            "formula": None,
        }
    )
    return steps


# ---------------------------------------------------------------------------
# Step-by-step explanation
# ---------------------------------------------------------------------------


def _build_steps(
    *,
    method: str,
    axis: str,
    variable: str,
    f_expression: str,
    g_expression: str,
    start: float,
    end: float,
    samples: int,
    panel_width: float,
    formula: str,
    setup: str,
    volume: float,
) -> list[dict]:
    axis_label = AXIS_LABELS[axis]
    a, b = _fmt(start), _fmt(end)
    steps: list[dict] = []

    if method == "discos":
        steps.append(
            {
                "title": "Región y eje de giro",
                "text": (
                    f"La región entre la curva f({variable}) y el {axis_label} "
                    f"se gira alrededor del {axis_label}, desde {variable} = {a} "
                    f"hasta {variable} = {b}. Cada corte perpendicular al eje "
                    "genera un disco."
                ),
                "formula": None,
            }
        )
        steps.append(
            {
                "title": "Fórmula del método de discos",
                "text": (
                    "El área de un disco de radio R es πR². Al integrar esas "
                    "áreas a lo largo del eje se acumula el volumen."
                ),
                "formula": f"V = π ∫[{a}, {b}] [R({variable})]² d{variable}",
            }
        )
        steps.append(
            {
                "title": "Radio del disco",
                "text": (
                    "El radio es la distancia desde la curva hasta el eje de "
                    "giro. Se usa el valor absoluto para que el radio sea "
                    "positivo aunque la curva quede por debajo del eje."
                ),
                "formula": f"R({variable}) = |{f_expression}|",
            }
        )
    elif method == "arandelas":
        steps.append(
            {
                "title": "Región y eje de giro",
                "text": (
                    f"La región entre R({variable}) y r({variable}) se gira "
                    f"alrededor del {axis_label}, desde {variable} = {a} hasta "
                    f"{variable} = {b}. Cada corte perpendicular al eje genera "
                    "una arandela: un disco con un hueco."
                ),
                "formula": None,
            }
        )
        steps.append(
            {
                "title": "Fórmula del método de arandelas",
                "text": (
                    "Al área del disco exterior se le resta el área del hueco "
                    "interior. Por eso aparece la diferencia de cuadrados."
                ),
                "formula": (
                    f"V = π ∫[{a}, {b}] "
                    f"([R({variable})]² − [r({variable})]²) d{variable}"
                ),
            }
        )
        steps.append(
            {
                "title": "Radios exterior e interior",
                "text": (
                    "R es la distancia de la curva exterior al eje y r la de la "
                    "curva interior. Debe cumplirse R ≥ r en todo el intervalo."
                ),
                "formula": (
                    f"R({variable}) = |{f_expression}|,  "
                    f"r({variable}) = |{g_expression}|"
                ),
            }
        )
    else:  # capas
        steps.append(
            {
                "title": "Región y eje de giro",
                "text": (
                    f"La región entre f({variable}) y g({variable}) se gira "
                    f"alrededor del {axis_label}, desde {variable} = {a} hasta "
                    f"{variable} = {b}. Cada corte paralelo al eje genera una "
                    "capa cilíndrica."
                ),
                "formula": None,
            }
        )
        steps.append(
            {
                "title": "Fórmula del método de capas",
                "text": (
                    "Una capa de radio ρ, altura h y espesor d"
                    f"{variable} tiene volumen aproximado 2πρh d{variable}. "
                    "Al integrar se suman todas las capas."
                ),
                "formula": (
                    f"V = 2π ∫[{a}, {b}] "
                    f"ρ({variable}) h({variable}) d{variable}"
                ),
            }
        )
        steps.append(
            {
                "title": "Radio de la capa",
                "text": (
                    "El radio es la distancia desde la capa hasta el eje de "
                    f"giro. Como el eje es el {axis_label}, el radio es "
                    f"ρ({variable}) = {variable}."
                ),
                "formula": f"ρ({variable}) = {variable}",
            }
        )
        steps.append(
            {
                "title": "Altura de la capa",
                "text": (
                    "La altura es la distancia entre la curva exterior y la "
                    "interior en cada punto."
                ),
                "formula": (
                    f"h({variable}) = f({variable}) − g({variable}) = "
                    f"({f_expression}) − ({g_expression})"
                ),
            }
        )

    steps.append(
        {
            "title": "Integral planteada",
            "text": (
                "Se sustituyen los radios (o el radio y la altura), la función "
                "y los límites de integración."
            ),
            "formula": setup,
        }
    )
    steps.append(
        {
            "title": "Integración numérica",
            "text": (
                f"Se aplica la regla de Simpson compuesta con n = {samples} "
                f"subintervalos de ancho h = {_fmt(panel_width)}. Simpson "
                "combina evaluaciones con pesos 1, 4, 2, 4, …, 1."
            ),
            "formula": (
                "V ≈ factor · (h/3) · [w₀·I₀ + w₁·I₁ + … + wₙ·Iₙ]"
            ),
        }
    )
    steps.append(
        {
            "title": "Resultado",
            "text": (
                f"El volumen del sólido es aproximadamente {_fmt(volume)} "
                "unidades cúbicas."
            ),
            "formula": f"V ≈ {_fmt(volume)} u³",
        }
    )
    steps.append(
        {
            "title": "Interpretación",
            "text": (
                "El eje de giro define la distancia de cada punto al eje y, por "
                "tanto, el volumen. Si giras la misma región alrededor de otro "
                "eje obtienes otro sólido y otro volumen; si usas otro método "
                "para el mismo sólido, el volumen debe coincidir."
            ),
            "formula": None,
        }
    )
    return steps
