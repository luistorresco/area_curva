from __future__ import annotations

import math
import random
import unittest

from curve_math import (
    area_between_curves,
    find_x_axis_intersections,
    integrate_points,
    validate_drawing,
)
from math_engine import (
    ExpressionEvaluationError,
    ExpressionSyntaxError,
    compile_expression,
    evaluate_expression,
)
from recognition import recognize_function


def curve_points(fn, start: float, end: float, intervals: int = 160, noise: float = 0.0):
    rng = random.Random(7)
    points = []
    for i in range(intervals + 1):
        x = start + (end - start) * i / intervals
        y = fn(x)
        if noise:
            y += rng.uniform(-noise, noise)
        points.append({"x": x, "y": y})
    return points


class DrawingValidationTests(unittest.TestCase):
    def test_straight_line_is_valid(self):
        result = validate_drawing(curve_points(lambda x: 2 * x + 1, -2, 2))
        self.assertEqual(result["status"], "valid")
        self.assertTrue(result["is_function"])

    def test_vertical_parabola_is_valid(self):
        result = validate_drawing(curve_points(lambda x: x * x, -2, 2))
        self.assertEqual(result["status"], "valid")

    def test_sine_is_valid(self):
        result = validate_drawing(curve_points(math.sin, -math.pi, math.pi))
        self.assertEqual(result["status"], "valid")

    def test_square_root_is_valid(self):
        result = validate_drawing(curve_points(math.sqrt, 0, 4))
        self.assertEqual(result["status"], "valid")

    def test_circle_is_not_a_function(self):
        points = [
            {"x": math.cos(t), "y": math.sin(t)}
            for t in [2 * math.pi * i / 120 for i in range(121)]
        ]
        result = validate_drawing(points)
        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["is_function"])
        self.assertEqual(result["reason_code"], "MULTIPLE_Y_FOR_X")
        self.assertTrue(result["diagnostics"]["ambiguous_regions"])

    def test_horizontal_parabola_is_not_a_function(self):
        points = [{"x": y * y / 4, "y": y} for y in [-2 + 4 * i / 120 for i in range(121)]]
        result = validate_drawing(points)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["reason_code"], "MULTIPLE_Y_FOR_X")

    def test_loop_is_not_a_function(self):
        points = [
            {"x": math.sin(t), "y": math.sin(2 * t)}
            for t in [2 * math.pi * i / 120 for i in range(121)]
        ]
        result = validate_drawing(points)
        self.assertEqual(result["status"], "invalid")

    def test_near_vertical_trace_is_invalid(self):
        points = [{"x": 0.001 * y, "y": y} for y in [-2 + 4 * i / 120 for i in range(121)]]
        result = validate_drawing(points)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["reason_code"], "VERTICAL_TRACE")

    def test_insufficient_points_is_uncertain(self):
        result = validate_drawing(curve_points(lambda x: x, 0, 1, intervals=4))
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["reason_code"], "INSUFFICIENT_POINTS")

    def test_moderate_noise_still_valid(self):
        result = validate_drawing(curve_points(math.sin, -math.pi, math.pi, noise=0.04))
        self.assertEqual(result["status"], "valid")

    def test_disconnected_trace_is_uncertain(self):
        points = curve_points(lambda x: x, -2, 0, intervals=60)
        points += curve_points(lambda x: x, 0.5, 2, intervals=60)
        result = validate_drawing(points)
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["reason_code"], "DISCONTINUOUS_TRACE")

    def test_invalid_coordinates_are_rejected(self):
        result = validate_drawing(
            [{"x": float("nan"), "y": 1.0}, {"x": 1.0, "y": 2.0}]
        )
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["reason_code"], "INVALID_COORDINATES")


class IntegrationTests(unittest.TestCase):
    def test_x_squared_integral(self):
        points = curve_points(lambda x: x * x, 0, 1, intervals=100)
        result = integrate_points(points)
        self.assertAlmostEqual(result["signed_integral"], 1 / 3, delta=2e-3)
        self.assertGreater(result["positive_area"], 0)
        self.assertAlmostEqual(result["negative_area"], 0.0, delta=1e-12)

    def test_linear_integral(self):
        result = integrate_points(curve_points(lambda x: x, 0, 1, intervals=80))
        self.assertAlmostEqual(result["signed_integral"], 0.5, delta=1e-9)

    def test_sine_integral(self):
        result = integrate_points(curve_points(math.sin, 0, math.pi, intervals=200))
        self.assertAlmostEqual(result["signed_integral"], 2.0, delta=1e-3)

    def test_crossing_is_split_into_positive_and_negative_areas(self):
        result = integrate_points([{"x": -1, "y": -1}, {"x": 1, "y": 1}])
        self.assertAlmostEqual(result["signed_integral"], 0.0, delta=1e-12)
        self.assertAlmostEqual(result["positive_area"], 0.5, delta=1e-12)
        self.assertAlmostEqual(result["negative_area"], -0.5, delta=1e-12)
        self.assertAlmostEqual(result["total_geometric_area"], 1.0, delta=1e-12)
        self.assertTrue(
            any(abs(point["x"]) < 1e-12 for point in result["processed_points"])
        )

    def test_always_negative_function(self):
        result = integrate_points(curve_points(lambda x: -1, 0, 2, intervals=10))
        self.assertAlmostEqual(result["signed_integral"], -2.0, delta=1e-9)
        self.assertAlmostEqual(result["positive_area"], 0.0, delta=1e-12)
        self.assertAlmostEqual(result["negative_area"], -2.0, delta=1e-9)
        self.assertAlmostEqual(result["total_geometric_area"], 2.0, delta=1e-9)

    def test_axis_intersections_are_interpolated(self):
        intersections = find_x_axis_intersections(
            [{"x": -1, "y": -2}, {"x": 1, "y": 2}]
        )
        self.assertEqual(len(intersections), 1)
        self.assertAlmostEqual(intersections[0]["x"], 0.0, delta=1e-12)

    def test_vertical_trace_cannot_be_integrated(self):
        with self.assertRaises(ValueError):
            integrate_points([{"x": 1, "y": 0}, {"x": 1, "y": 1}])


class RecognitionTests(unittest.TestCase):
    def _assert_recognized(self, fn, start, end, max_relative=0.05):
        result = recognize_function(curve_points(fn, start, end))
        self.assertEqual(result["validation"]["status"], "valid")
        self.assertTrue(result["recognized"], result)
        self.assertIsNotNone(result["expression"])
        self.assertLess(result["metrics"]["relative_error"], max_relative)
        compiled = compile_expression(result["expression"])
        for x in (start, (start + end) / 2, end):
            self.assertTrue(math.isfinite(compiled.evaluate(x)))

    def test_quadratic(self):
        self._assert_recognized(lambda x: x * x + 2, -2, 2)

    def test_linear(self):
        self._assert_recognized(lambda x: 2 * x + 1, -2, 2)

    def test_sine(self):
        self._assert_recognized(math.sin, -math.pi, math.pi)

    def test_square_root(self):
        self._assert_recognized(math.sqrt, 0, 4)

    def test_exponential(self):
        self._assert_recognized(math.exp, 0, 2)

    def test_absolute_value(self):
        self._assert_recognized(abs, -2, 2)

    def test_noisy_sine(self):
        result = recognize_function(
            curve_points(math.sin, -math.pi, math.pi, noise=0.02)
        )
        self.assertTrue(result["recognized"], result)
        self.assertLess(result["metrics"]["relative_error"], 0.05)

    def test_insufficient_data_does_not_recognize(self):
        result = recognize_function(curve_points(lambda x: x, 0, 1, intervals=4))
        self.assertFalse(result["recognized"])
        self.assertEqual(result["status"], "uncertain")

    def test_invalid_drawing_does_not_recognize(self):
        points = [
            {"x": math.cos(t), "y": math.sin(t)}
            for t in [2 * math.pi * i / 60 for i in range(61)]
        ]
        result = recognize_function(points)
        self.assertFalse(result["recognized"])
        self.assertEqual(result["status"], "invalid")

    def test_unmatched_curve_returns_metrics_not_a_guarantee(self):
        result = recognize_function(
            curve_points(lambda x: math.sin(5 * x) + x**3, -2, 2)
        )
        self.assertIn(result["status"], {"success", "low_confidence", "no_fit"})
        if result["metrics"] is not None:
            self.assertGreaterEqual(result["metrics"]["relative_error"], 0.0)
        self.assertTrue(result["warnings"])


class AreaBetweenCurvesTests(unittest.TestCase):
    def _area(self, f, g, start, end, samples=2000):
        return area_between_curves(
            compile_expression(f), compile_expression(g), start, end, samples
        )

    def test_line_and_parabola(self):
        result = self._area("x", "x**2", 0, 1)
        self.assertAlmostEqual(result["total_area"], 1 / 6, delta=1e-4)
        self.assertEqual(len(result["intersections"]), 2)

    def test_two_lines_crossing_midpoint(self):
        result = self._area("x", "1 - x", 0, 1)
        self.assertAlmostEqual(result["total_area"], 0.5, delta=1e-4)
        self.assertEqual(len(result["intervals"]), 2)
        self.assertAlmostEqual(
            sum(interval["area"] for interval in result["intervals"]),
            result["total_area"],
            delta=1e-9,
        )

    def test_curves_without_crossing(self):
        result = self._area("x**2", "4", -1, 1)
        self.assertAlmostEqual(result["total_area"], 22 / 3, delta=1e-3)
        self.assertEqual(len(result["intersections"]), 0)

    def test_multiple_intersections(self):
        result = self._area("sin(x)", "0", 0, 4 * math.pi)
        self.assertAlmostEqual(result["total_area"], 8.0, delta=1e-3)
        self.assertEqual(len(result["intersections"]), 5)
        self.assertEqual(len(result["intervals"]), 4)

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            self._area("x", "x**2", 1, 0)

    def test_domain_error_is_reported(self):
        with self.assertRaises(ExpressionEvaluationError):
            self._area("sqrt(x)", "0", -1, 1)

    def test_identical_curves(self):
        result = self._area("x", "x", 0, 1)
        self.assertAlmostEqual(result["total_area"], 0.0, delta=1e-9)


class ExpressionSecurityTests(unittest.TestCase):
    def test_rejects_import(self):
        with self.assertRaises(ExpressionSyntaxError):
            compile_expression("__import__('os').system('echo hi')")

    def test_rejects_open(self):
        with self.assertRaises(ExpressionSyntaxError):
            compile_expression("open('secret.txt')")

    def test_rejects_attribute_access(self):
        with self.assertRaises(ExpressionSyntaxError):
            compile_expression("x.real")

    def test_rejects_long_expression(self):
        with self.assertRaises(ExpressionSyntaxError):
            compile_expression("x+" * 120 + "x")

    def test_division_by_zero_is_evaluation_error(self):
        compiled = compile_expression("1 / x")
        with self.assertRaises(ExpressionEvaluationError):
            compiled.evaluate(0.0)

    def test_complex_result_is_rejected(self):
        compiled = compile_expression("(-1) ** 0.5")
        with self.assertRaises(ExpressionEvaluationError):
            compiled.evaluate(0.0)

    def test_large_factorial_is_bounded(self):
        compiled = compile_expression("factorial(1000)")
        with self.assertRaises(ExpressionEvaluationError):
            compiled.evaluate(0.0)

    def test_large_power_is_bounded(self):
        compiled = compile_expression("2 ** 10000")
        with self.assertRaises(ExpressionEvaluationError):
            compiled.evaluate(0.0)

    def test_allowed_function_works(self):
        self.assertAlmostEqual(evaluate_expression("sin(pi / 2)", 0), 1.0)


if __name__ == "__main__":
    unittest.main()
