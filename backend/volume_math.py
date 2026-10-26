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
