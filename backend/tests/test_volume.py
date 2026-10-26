from __future__ import annotations

import math
import unittest

from math_engine import (
    ExpressionEvaluationError,
    ExpressionSyntaxError,
    compile_expression,
)
from volume_math import integration_variable, volume_from_profile, volume_solid


class VolumeMethodTests(unittest.TestCase):
    def _volume(self, method, axis, f, g="0", start=0.0, end=1.0, samples=2000):
        return volume_solid(method, axis, f, g, start, end, samples)

    def test_discs_around_x_axis(self):
        result = self._volume("discos", "x", "x", "0", 0, 2)
        self.assertAlmostEqual(result["volume"], 8 * math.pi / 3, delta=1e-8)
        self.assertEqual(result["variable"], "x")

    def test_discs_around_y_axis(self):
        result = self._volume("discos", "y", "y**2", "0", 0, 2)
        self.assertAlmostEqual(result["volume"], 32 * math.pi / 5, delta=1e-8)
        self.assertEqual(result["variable"], "y")

    def test_washers_around_x_axis(self):
        result = self._volume("arandelas", "x", "2", "1", 0, 3)
        self.assertAlmostEqual(result["volume"], 9 * math.pi, delta=1e-8)

    def test_washers_around_y_axis(self):
        result = self._volume("arandelas", "y", "2", "1", 0, 3)
        self.assertAlmostEqual(result["volume"], 9 * math.pi, delta=1e-8)

    def test_shells_around_y_axis(self):
        result = self._volume("capas", "y", "x**2", "0", 0, 1)
        self.assertAlmostEqual(result["volume"], math.pi / 2, delta=1e-8)
        self.assertEqual(result["variable"], "x")

    def test_shells_around_x_axis(self):
        result = self._volume("capas", "x", "1", "0", 0, 3)
        self.assertAlmostEqual(result["volume"], 9 * math.pi, delta=1e-8)
        self.assertEqual(result["variable"], "y")

    def test_discs_and_shells_agree_around_y_axis(self):
        shells = self._volume("capas", "y", "x**2", "0", 0, 1)
        discs = self._volume("discos", "y", "sqrt(y)", "0", 0, 1)
        self.assertAlmostEqual(shells["volume"], discs["volume"], delta=1e-8)
        self.assertAlmostEqual(shells["volume"], math.pi / 2, delta=1e-8)

    def test_discs_and_shells_agree_around_x_axis(self):
        discs = self._volume("discos", "x", "x**2", "0", 0, 1)
        shells = self._volume("capas", "x", "1", "sqrt(y)", 0, 1)
        self.assertAlmostEqual(discs["volume"], shells["volume"], delta=1e-8)
        self.assertAlmostEqual(discs["volume"], math.pi / 5, delta=1e-8)

    def test_same_region_different_axes_gives_different_volume(self):
        about_x = self._volume("discos", "x", "x**2", "0", 0, 1)
        about_y = self._volume("capas", "y", "x**2", "0", 0, 1)
        self.assertAlmostEqual(about_x["volume"], math.pi / 5, delta=1e-8)
        self.assertAlmostEqual(about_y["volume"], math.pi / 2, delta=1e-8)
        self.assertNotAlmostEqual(about_x["volume"], about_y["volume"], places=3)

    def test_integration_variable_mapping(self):
        self.assertEqual(integration_variable("discos", "x"), "x")
        self.assertEqual(integration_variable("discos", "y"), "y")
        self.assertEqual(integration_variable("arandelas", "x"), "x")
        self.assertEqual(integration_variable("arandelas", "y"), "y")
        self.assertEqual(integration_variable("capas", "x"), "y")
        self.assertEqual(integration_variable("capas", "y"), "x")

    def test_odd_samples_are_adjusted_for_simpson(self):
        result = self._volume("discos", "x", "x", "0", 0, 2, samples=201)
        self.assertEqual(result["samples_used"] % 2, 0)
        self.assertAlmostEqual(result["volume"], 8 * math.pi / 3, delta=1e-8)

    def test_response_contains_steps_and_points(self):
        result = self._volume("capas", "y", "x**2", "0", 0, 1)
        self.assertTrue(result["steps"])
        self.assertEqual(result["steps"][0]["title"], "Región y eje de giro")
        self.assertTrue(any("Interpretación" == step["title"] for step in result["steps"]))
        self.assertGreater(len(result["f_points"]), 2)
        self.assertGreater(len(result["g_points"]), 2)

    def test_discs_accept_negative_function(self):
        result = self._volume("discos", "x", "-x", "0", 0, 2)
        self.assertAlmostEqual(result["volume"], 8 * math.pi / 3, delta=1e-8)
        self.assertTrue(result["warnings"])

    def test_washers_reject_reversed_radii(self):
        with self.assertRaises(ValueError) as context:
            self._volume("arandelas", "x", "x", "2", 0, 1)
        self.assertIn("radio exterior", str(context.exception).lower())

    def test_washers_reject_region_crossing_axis(self):
        with self.assertRaises(ValueError):
            self._volume("arandelas", "x", "1", "-1", 0, 1)

    def test_shells_reject_negative_interval(self):
        with self.assertRaises(ValueError):
            self._volume("capas", "y", "x", "0", -1, 1)

    def test_shells_reject_reversed_curves(self):
        with self.assertRaises(ValueError):
            self._volume("capas", "y", "0", "1", 0, 1)

    def test_rejects_bad_interval(self):
        with self.assertRaises(ValueError):
            self._volume("discos", "x", "x", "0", 2, 1)

    def test_rejects_bad_method_and_axis(self):
        with self.assertRaises(ValueError):
            volume_solid("conos", "x", "x", "0", 0, 1)
        with self.assertRaises(ValueError):
            volume_solid("discos", "z", "x", "0", 0, 1)

    def test_rejects_bad_expression(self):
        with self.assertRaises(ExpressionSyntaxError):
            self._volume("discos", "x", "__import__('os')", "0", 0, 1)

    def test_reports_domain_error(self):
        with self.assertRaises(ExpressionEvaluationError):
            self._volume("discos", "x", "sqrt(x)", "0", -1, 1)


class ProfileVolumeTests(unittest.TestCase):
    @staticmethod
    def _line_points(start=0.0, end=2.0, count=200):
        return [
            {
                "x": start + (end - start) * index / count,
                "y": start + (end - start) * index / count,
            }
            for index in range(count + 1)
        ]

    def _volume(self, method, axis, points=None, samples=800):
        return volume_from_profile(
            method=method,
            axis=axis,
            points=points or self._line_points(),
            samples=samples,
            f_expression="x",
            source="function",
        )

    def test_profile_discs_around_x(self):
        result = self._volume("discos", "x")
        self.assertAlmostEqual(result["volume"], 8 * math.pi / 3, delta=1e-2)
        self.assertEqual(result["variable"], "x")
        self.assertTrue(result["profile"])
        self.assertTrue(result["profile_points"])
        self.assertTrue(result["steps"])

    def test_profile_washers_around_x_matches_discs(self):
        discs = self._volume("discos", "x")
        washers = self._volume("arandelas", "x")
        self.assertAlmostEqual(discs["volume"], washers["volume"], delta=1e-6)

    def test_profile_shells_around_y(self):
        result = self._volume("capas", "y")
        self.assertAlmostEqual(result["volume"], 16 * math.pi / 3, delta=1e-2)
        self.assertEqual(result["variable"], "x")
        self.assertEqual(result["start"], 0.0)
        self.assertEqual(result["end"], 2.0)

    def test_profile_washers_around_y_matches_shells(self):
        shells = self._volume("capas", "y")
        washers = self._volume("arandelas", "y")
        self.assertAlmostEqual(shells["volume"], washers["volume"], delta=1e-2)
        self.assertEqual(washers["variable"], "y")

    def test_profile_shells_around_x_matches_discs(self):
        discs = self._volume("discos", "x")
        shells = self._volume("capas", "x")
        self.assertAlmostEqual(discs["volume"], shells["volume"], delta=1e-2)
        self.assertEqual(shells["variable"], "y")

    def test_profile_discs_around_y_uses_outer_envelope(self):
        result = self._volume("discos", "y")
        self.assertAlmostEqual(result["volume"], 8 * math.pi, delta=1e-2)
        self.assertEqual(result["variable"], "y")
        self.assertTrue(result["warnings"])

    def test_profile_axes_give_different_volumes(self):
        about_x = self._volume("discos", "x")
        about_y = self._volume("capas", "y")
        self.assertNotAlmostEqual(about_x["volume"], about_y["volume"], places=2)

    def test_profile_keeps_stroke_when_method_changes(self):
        # y = x is deliberately not symmetric: a naive x/y swap would use
        # the wrong height for the shells around Y.
        discs = self._volume("discos", "x")
        shells = self._volume("capas", "y")
        self.assertAlmostEqual(discs["volume"], 8 * math.pi / 3, delta=1e-2)
        self.assertAlmostEqual(shells["volume"], 16 * math.pi / 3, delta=1e-2)

    def test_profile_shells_reflect_negative_stroke(self):
        points = self._line_points(-2.0, 0.0)
        result = self._volume("capas", "y", points=points)
        self.assertAlmostEqual(result["volume"], 16 * math.pi / 3, delta=1e-2)
        self.assertTrue(any("reflej" in warning for warning in result["warnings"]))

    def test_profile_rejects_flat_or_empty_curve(self):
        with self.assertRaises(ValueError):
            volume_from_profile(
                "discos",
                "x",
                points=[{"x": 0, "y": 0}, {"x": 0, "y": 1}],
            )
        with self.assertRaises(ValueError):
            volume_from_profile("discos", "x", points=[{"x": 0, "y": 0}])

    def test_profile_rejects_interval_outside_stroke(self):
        with self.assertRaises(ValueError):
            volume_from_profile(
                "discos",
                "x",
                points=self._line_points(),
                start=0,
                end=3,
            )


class VariableExpressionTests(unittest.TestCase):
    def test_y_variable_is_supported(self):
        compiled = compile_expression("y**2 + 1", variable="y")
        self.assertAlmostEqual(compiled.evaluate(3), 10.0)

    def test_wrong_variable_is_rejected(self):
        with self.assertRaises(ExpressionSyntaxError):
            compile_expression("x**2", variable="y")

    def test_default_variable_remains_x(self):
        compiled = compile_expression("x + 1")
        self.assertAlmostEqual(compiled.evaluate(2), 3.0)


if __name__ == "__main__":
    unittest.main()
