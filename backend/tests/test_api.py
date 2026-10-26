from __future__ import annotations

import math
import unittest

from fastapi import HTTPException

import main
from schemas import (
    AreaBetweenRequest,
    AreaBetweenResponse,
    CalculationResult,
    CurveRequest,
    DrawingValidation,
    FunctionRequest,
    RecognitionResponse,
    VolumeProfileRequest,
    VolumeRequest,
    VolumeResponse,
)


def line_points(start=-2, end=2, intervals=80):
    return [
        {"x": start + (end - start) * i / intervals, "y": 2 * (start + (end - start) * i / intervals) + 1}
        for i in range(intervals + 1)
    ]


class ApiContractTests(unittest.TestCase):
    def test_health(self):
        self.assertEqual(main.health(), {"status": "ok"})

    def test_validate_drawing_contract(self):
        response = main.validate_drawing(CurveRequest(points=line_points()))
        validated = DrawingValidation(**response)
        self.assertEqual(validated.status, "valid")
        self.assertTrue(validated.is_function)

    def test_calculate_contract(self):
        response = main.calculate_area(CurveRequest(points=line_points(0, 1)))
        result = CalculationResult(**response)
        self.assertTrue(result.has_valid_result)
        self.assertGreater(result.total_geometric_area, 0)

    def test_calculate_invalid_input_returns_400(self):
        with self.assertRaises(HTTPException) as context:
            main.calculate_area(
                CurveRequest(points=[{"x": 1, "y": 0}, {"x": 1, "y": 1}])
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_evaluate_function_contract(self):
        response = main.evaluate_function(
            FunctionRequest(expression="sin(x)", start=0, end=math.pi, samples=40)
        )
        self.assertEqual(len(response["points"]), 41)
        self.assertAlmostEqual(response["points"][-1]["y"], 0.0, places=10)

    def test_evaluate_function_rejects_bad_expression(self):
        with self.assertRaises(HTTPException) as context:
            main.evaluate_function(
                FunctionRequest(expression="__import__('os')", start=0, end=1, samples=10)
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_evaluate_function_reports_domain_error(self):
        with self.assertRaises(HTTPException) as context:
            main.evaluate_function(
                FunctionRequest(expression="sqrt(x)", start=-1, end=1, samples=10)
            )
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("x =", context.exception.detail)

    def test_evaluate_function_rejects_bad_interval(self):
        with self.assertRaises(HTTPException) as context:
            main.evaluate_function(
                FunctionRequest(expression="x", start=1, end=0, samples=10)
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_recognize_contract(self):
        response = main.recognize(CurveRequest(points=line_points()))
        result = RecognitionResponse(**response)
        self.assertTrue(result.recognized)
        self.assertEqual(result.validation.status, "valid")

    def test_area_between_contract(self):
        response = main.area_between(
            AreaBetweenRequest(
                f_expression="x",
                g_expression="x**2",
                start=0,
                end=1,
                samples=500,
            )
        )
        result = AreaBetweenResponse(**response)
        self.assertAlmostEqual(result.total_area, 1 / 6, delta=1e-3)
        self.assertGreater(len(result.f_points), 2)

    def test_area_between_rejects_domain_error(self):
        with self.assertRaises(HTTPException) as context:
            main.area_between(
                AreaBetweenRequest(
                    f_expression="sqrt(x)",
                    g_expression="0",
                    start=-1,
                    end=1,
                    samples=100,
                )
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_area_between_rejects_bad_expression(self):
        with self.assertRaises(HTTPException) as context:
            main.area_between(
                AreaBetweenRequest(
                    f_expression="x.real",
                    g_expression="0",
                    start=0,
                    end=1,
                    samples=100,
                )
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_volume_contract(self):
        response = main.volume(
            VolumeRequest(
                method="discos",
                axis="x",
                f_expression="x",
                g_expression="0",
                start=0,
                end=2,
                samples=500,
            )
        )
        result = VolumeResponse(**response)
        self.assertTrue(result.has_valid_result)
        self.assertAlmostEqual(result.volume, 8 * math.pi / 3, delta=1e-7)
        self.assertEqual(result.variable, "x")
        self.assertTrue(result.steps)

    def test_volume_shells_around_y_contract(self):
        response = main.volume(
            VolumeRequest(
                method="capas",
                axis="y",
                f_expression="x**2",
                g_expression="0",
                start=0,
                end=1,
                samples=500,
            )
        )
        result = VolumeResponse(**response)
        self.assertAlmostEqual(result.volume, math.pi / 2, delta=1e-7)
        self.assertEqual(result.variable, "x")

    def test_volume_rejects_bad_expression(self):
        with self.assertRaises(HTTPException) as context:
            main.volume(
                VolumeRequest(
                    method="discos",
                    axis="x",
                    f_expression="x.real",
                    start=0,
                    end=1,
                    samples=100,
                )
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_volume_rejects_reversed_radii(self):
        with self.assertRaises(HTTPException) as context:
            main.volume(
                VolumeRequest(
                    method="arandelas",
                    axis="x",
                    f_expression="x",
                    g_expression="2",
                    start=0,
                    end=1,
                    samples=100,
                )
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_volume_profile_contract(self):
        points = [
            {"x": 2 * index / 100, "y": 2 * index / 100}
            for index in range(101)
        ]
        response = main.volume_profile(
            VolumeProfileRequest(
                method="capas",
                axis="y",
                points=points,
                samples=400,
                f_expression="x",
                source="draw",
            )
        )
        result = VolumeResponse(**response)
        self.assertTrue(result.profile)
        self.assertAlmostEqual(result.volume, 16 * math.pi / 3, delta=1e-1)
        self.assertEqual(result.variable, "x")
        self.assertTrue(result.profile_points)
        self.assertTrue(result.steps)

    def test_volume_profile_without_expression_uses_drawn_curve(self):
        points = [
            {"x": -1 + 2 * index / 20, "y": 1 + index / 20}
            for index in range(21)
        ]
        response = main.volume_profile(
            VolumeProfileRequest(
                method="discos",
                axis="x",
                points=points,
                samples=200,
                f_expression=None,
                source="draw",
            )
        )
        result = VolumeResponse(**response)
        self.assertEqual(result.f_expression, "trazo dibujado")
        self.assertTrue(
            any("trazo dibujado arriba" in step.text for step in result.steps)
        )
        self.assertFalse(
            any("modo manual" in step.text for step in result.steps)
        )

    def test_volume_profile_rejects_degenerate_stroke(self):
        with self.assertRaises(HTTPException) as context:
            main.volume_profile(
                VolumeProfileRequest(
                    method="discos",
                    axis="x",
                    points=[{"x": 0, "y": 0}, {"x": 0, "y": 1}],
                    samples=100,
                )
            )
        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
