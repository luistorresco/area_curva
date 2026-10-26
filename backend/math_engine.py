"""Safe expression parser and evaluator shared by all math endpoints.

Only a small whitelist of AST nodes, operators, functions and constants is
accepted.  No ``eval``/``exec`` is used, and expensive operations (powers and
factorials) are bounded before they can exhaust memory or CPU.
"""

from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass
from typing import Callable, Iterable

MAX_EXPRESSION_LENGTH = 200
MAX_AST_NODES = 300
MAX_POWER_ABS = 512
MAX_FACTORIAL = 170


class ExpressionError(ValueError):
    """Base error for invalid or non-evaluable expressions."""


class ExpressionSyntaxError(ExpressionError):
    pass


class ExpressionEvaluationError(ExpressionError):
    def __init__(self, message: str, x: float | None = None):
        self.x = x
        super().__init__(message)


def _safe_factorial(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("factorial requiere un valor finito")
    n = int(round(value))
    if n < 0:
        raise ValueError("factorial no está definido para números negativos")
    if n > MAX_FACTORIAL:
        raise ValueError(f"factorial se limita a {MAX_FACTORIAL}")
    return float(math.factorial(n))


def _safe_pow(base: float, exponent: float) -> float:
    if not math.isfinite(base) or not math.isfinite(exponent):
        raise ValueError("la potencia requiere valores finitos")
    if abs(exponent) > MAX_POWER_ABS:
        raise ValueError(f"el exponente absoluto se limita a {MAX_POWER_ABS}")
    try:
        result = math.pow(float(base), float(exponent))
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"potencia no válida: {exc}") from exc
    if not math.isfinite(result):
        raise ValueError("la potencia produce un valor no finito")
    return result


def _cbrt(value: float) -> float:
    return math.copysign(abs(value) ** (1.0 / 3.0), value)


ALLOWED_FUNCTIONS: dict[str, Callable[..., float]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sqrt": math.sqrt,
    "cbrt": _cbrt,
    "abs": abs,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": _safe_factorial,
    "radians": math.radians,
    "degrees": math.degrees,
    "pow": _safe_pow,
    "hypot": math.hypot,
}

TWO_ARG_FUNCTIONS = {"atan2", "hypot", "pow"}

ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

AST_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: _safe_pow,
}

AST_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _as_float(value: float | int) -> float:
    if isinstance(value, complex):
        raise ValueError("el resultado no es un número real")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("el resultado no es un número real finito") from exc
    if not math.isfinite(result):
        raise ValueError("el resultado no es finito")
    return result


def _validate_node(node: ast.AST, count: list[int], variable: str = "x") -> None:
    count[0] += 1
    if count[0] > MAX_AST_NODES:
        raise ExpressionSyntaxError("La expresión es demasiado compleja.")

    if isinstance(node, ast.Expression):
        _validate_node(node.body, count, variable)
    elif isinstance(node, ast.Constant):
        if type(node.value) not in (int, float):
            raise ExpressionSyntaxError("Solo se permiten números reales.")
    elif isinstance(node, ast.Name):
        name = node.id.lower()
        if name != variable and name not in ALLOWED_CONSTANTS:
            raise ExpressionSyntaxError(f"Nombre no permitido: '{node.id}'.")
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in AST_BINARY_OPERATORS:
            raise ExpressionSyntaxError("Operador no permitido.")
        _validate_node(node.left, count, variable)
        _validate_node(node.right, count, variable)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in AST_UNARY_OPERATORS:
            raise ExpressionSyntaxError("Operador unario no permitido.")
        _validate_node(node.operand, count, variable)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise ExpressionSyntaxError("Solo se permiten llamadas directas a funciones.")
        name = node.func.id.lower()
        if name not in ALLOWED_FUNCTIONS:
            raise ExpressionSyntaxError(f"Función no permitida: '{node.func.id}'.")
        expected = 2 if name in TWO_ARG_FUNCTIONS else 1
        if len(node.args) != expected:
            raise ExpressionSyntaxError(f"'{node.func.id}' recibe {expected} argumento(s).")
        for arg in node.args:
            _validate_node(arg, count, variable)
    else:
        raise ExpressionSyntaxError(f"Expresión no válida: '{type(node).__name__}'.")


def _eval_node(node: ast.AST, value: float, variable: str = "x") -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, value, variable)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        name = node.id.lower()
        if name == variable:
            return value
        return ALLOWED_CONSTANTS[name]
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, value, variable)
        right = _eval_node(node.right, value, variable)
        return _as_float(AST_BINARY_OPERATORS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp):
        return _as_float(
            AST_UNARY_OPERATORS[type(node.op)](
                _eval_node(node.operand, value, variable)
            )
        )
    if isinstance(node, ast.Call):
        name = node.func.id.lower()
        args = [_eval_node(arg, value, variable) for arg in node.args]
        return _as_float(ALLOWED_FUNCTIONS[name](*args))
    raise ExpressionError("Expresión no válida.")


@dataclass(frozen=True)
class CompiledExpression:
    source: str
    tree: ast.Expression
    variable: str = "x"

    def evaluate(self, value: float) -> float:
        if not math.isfinite(value):
            raise ExpressionEvaluationError(
                f"El valor de {self.variable} debe ser finito.", x=value
            )
        try:
            return _eval_node(self.tree, float(value), self.variable)
        except ExpressionError:
            raise
        except (ZeroDivisionError, OverflowError, ValueError, TypeError) as exc:
            raise ExpressionEvaluationError(str(exc), x=value) from exc


def compile_expression(
    expression: str, variable: str = "x"
) -> CompiledExpression:
    """Parse and validate an expression, returning an evaluable object.

    ``variable`` selects the free variable (``x`` by default).  Volume
    calculations that integrate along the Y axis use ``variable="y"``.
    """

    source = (expression or "").strip()
    if not source:
        raise ExpressionSyntaxError("La expresión está vacía.")
    if len(source) > MAX_EXPRESSION_LENGTH:
        raise ExpressionSyntaxError(
            f"La expresión es demasiado larga (máximo {MAX_EXPRESSION_LENGTH} caracteres)."
        )

    variable = (variable or "x").strip().lower()
    if (
        not variable.isidentifier()
        or variable in ALLOWED_CONSTANTS
        or variable in ALLOWED_FUNCTIONS
    ):
        raise ExpressionSyntaxError(f"Variable no permitida: '{variable}'.")

    cleaned = source.replace("^", "**")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ExpressionSyntaxError("La sintaxis de la función no es válida.") from exc

    _validate_node(tree, [0], variable)
    return CompiledExpression(source=source, tree=tree, variable=variable)


def evaluate_expression(expression: str, x: float) -> float:
    return compile_expression(expression).evaluate(x)


def sample_expression(
    compiled: CompiledExpression, start: float, end: float, samples: int
) -> list[dict[str, float]]:
    """Sample a compiled expression at ``samples`` intervals.

    Returns ``samples + 1`` points, including both endpoints.  Domain errors
    are reported with the x value that failed so the UI can explain them.
    """

    if not math.isfinite(start) or not math.isfinite(end):
        raise ExpressionEvaluationError("Los límites deben ser números finitos.")
    if start >= end:
        raise ExpressionEvaluationError("El inicio del intervalo debe ser menor que el fin.")
    if samples < 2:
        raise ExpressionEvaluationError("Se necesitan al menos 2 muestras.")

    step = (end - start) / samples
    points: list[dict[str, float]] = []
    for i in range(samples + 1):
        x = start + step * i
        try:
            y = compiled.evaluate(x)
        except ExpressionEvaluationError as exc:
            raise ExpressionEvaluationError(
                f"No se pudo evaluar la función en x = {x:.6g}: {exc}", x=x
            ) from exc
        if not math.isfinite(y):
            raise ExpressionEvaluationError(
                f"La función produce un valor no finito en x = {x:.6g}.", x=x
            )
        points.append({"x": x, "y": y})
    return points


def evaluate_on_grid(
    compiled: CompiledExpression, xs: Iterable[float]
) -> tuple[list[float], list[float]]:
    """Evaluate an expression on an explicit grid, returning finite xs/ys."""

    out_x: list[float] = []
    out_y: list[float] = []
    for x in xs:
        try:
            y = compiled.evaluate(x)
        except ExpressionEvaluationError as exc:
            raise ExpressionEvaluationError(
                f"No se pudo evaluar la función en x = {x:.6g}: {exc}", x=x
            ) from exc
        if not math.isfinite(y):
            raise ExpressionEvaluationError(
                f"La función produce un valor no finito en x = {x:.6g}.", x=x
            )
        out_x.append(float(x))
        out_y.append(y)
    return out_x, out_y
