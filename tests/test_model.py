"""model 模块单元测试：坐标公式、闭合周期、采样与参数校验。"""

from __future__ import annotations

import math
import unittest

from spirodraw.model import (
    MAX_POINTS,
    MAX_TURNS,
    MIN_SAMPLES_PER_TURN,
    Params,
    SpirodrawError,
    bounds,
    count_distinct,
    format_number,
    point_at,
    sample_count,
    sample_points,
    visual_distance,
    visual_signature,
)


class PointFormulaTest(unittest.TestCase):
    def test_start_point(self) -> None:
        params = Params(8, 3, 2)
        x, y = point_at(params, 0.0)
        self.assertAlmostEqual(x, 7.0, places=12)
        self.assertAlmostEqual(y, 0.0, places=12)

    def test_quarter_turn(self) -> None:
        params = Params(8, 3, 2)
        x, y = point_at(params, math.pi / 2.0)
        self.assertAlmostEqual(x, 2.0 * math.cos(5.0 * math.pi / 6.0), places=12)
        self.assertAlmostEqual(y, 5.0 - 2.0 * math.sin(5.0 * math.pi / 6.0), places=12)

    def test_general_angle_matches_formula(self) -> None:
        params = Params(11, 4, 2.5)
        t = 0.37
        ratio = (11.0 - 4.0) / 4.0
        expected_x = 7.0 * math.cos(t) + 2.5 * math.cos(ratio * t)
        expected_y = 7.0 * math.sin(t) - 2.5 * math.sin(ratio * t)
        x, y = point_at(params, t)
        self.assertAlmostEqual(x, expected_x, places=12)
        self.assertAlmostEqual(y, expected_y, places=12)

    def test_ratio_uses_radius_difference(self) -> None:
        params = Params(10, 4, 3)
        self.assertAlmostEqual(params.rotation_ratio, 1.5, places=12)
        x, _ = point_at(params, 0.0)
        self.assertAlmostEqual(x, 9.0, places=12)

    def test_invalid_time_type(self) -> None:
        params = Params(8, 3, 2)
        with self.assertRaises(SpirodrawError):
            point_at(params, "0.5")  # type: ignore[arg-type]

    def test_invalid_params_object(self) -> None:
        with self.assertRaises(SpirodrawError):
            point_at("not-params", 0.0)  # type: ignore[arg-type]


class PeriodTest(unittest.TestCase):
    def test_two_turns(self) -> None:
        self.assertEqual(Params(9, 6, 3).period_turns, 2)

    def test_three_turns(self) -> None:
        self.assertEqual(Params(7, 3, 2).period_turns, 3)

    def test_four_turns(self) -> None:
        self.assertEqual(Params(11, 4, 2).period_turns, 4)

    def test_gcd_shortens_period(self) -> None:
        self.assertEqual(Params(12, 8, 2).period_turns, 2)

    def test_decimal_radius(self) -> None:
        self.assertEqual(Params(7.5, 2.5, 1.5).period_turns, 1)
        self.assertEqual(Params(8.4, 2.4, 1.2).period_turns, 2)

    def test_period_is_integer(self) -> None:
        self.assertIsInstance(Params(9, 6, 3).period_turns, int)


class SamplingTest(unittest.TestCase):
    def test_default_sample_count(self) -> None:
        params = Params(9, 6, 3)
        self.assertEqual(sample_count(params), params.period_turns * 180 + 1)

    def test_custom_sample_count(self) -> None:
        params = Params(9, 6, 3)
        self.assertEqual(sample_count(params, 30), params.period_turns * 30 + 1)

    def test_last_point_equals_first(self) -> None:
        points = sample_points(Params(9, 6, 3), 30)
        self.assertEqual(points[0], points[-1])

    def test_closure_after_period(self) -> None:
        params = Params(7, 3, 2)
        x0, y0 = point_at(params, 0.0)
        x1, y1 = point_at(params, 2.0 * math.pi * params.period_turns)
        self.assertLess(abs(x1 - x0), 1e-9)
        self.assertLess(abs(y1 - y0), 1e-9)

    def test_shifted_angle_repeats(self) -> None:
        params = Params(9, 6, 3)
        x0, y0 = point_at(params, 0.4)
        x1, y1 = point_at(
            params, 0.4 + 2.0 * math.pi * params.period_turns
        )
        self.assertLess(abs(x1 - x0), 1e-9)
        self.assertLess(abs(y1 - y0), 1e-9)

    def test_all_points_finite(self) -> None:
        for x, y in sample_points(Params(13, 5, 4), 24):
            self.assertTrue(math.isfinite(x))
            self.assertTrue(math.isfinite(y))

    def test_enough_distinct_points(self) -> None:
        points = sample_points(Params(9, 6, 3), 24)
        self.assertGreaterEqual(count_distinct(points), 3)

    def test_invalid_sample_counts(self) -> None:
        params = Params(9, 6, 3)
        for value in (0, MIN_SAMPLES_PER_TURN - 1, 721, True, 12.0):
            with self.assertRaises(SpirodrawError):
                sample_points(params, value)  # type: ignore[arg-type]

    def test_too_many_points(self) -> None:
        params = Params(41, 20, 10)
        self.assertEqual(params.period_turns, MAX_TURNS)
        with self.assertRaises(SpirodrawError) as ctx:
            sample_points(params, 720)
        self.assertIn("采样点过多", str(ctx.exception))
        self.assertGreater(params.period_turns * 720 + 1, MAX_POINTS)


class ParamsValidationTest(unittest.TestCase):
    def test_radius_must_be_greater(self) -> None:
        with self.assertRaises(SpirodrawError) as ctx:
            Params(3, 3, 1)
        self.assertIn("大于", str(ctx.exception))

    def test_radius_positive(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params(5, 0, 1)

    def test_pen_distance_positive(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params(5, 2, 0)

    def test_pen_distance_not_beyond_radius(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params(5, 2, 3)

    def test_bool_is_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params(True, 2, 1)  # type: ignore[arg-type]

    def test_text_is_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params("7", 2, 1)  # type: ignore[arg-type]

    def test_infinite_value_is_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params(float("inf"), 2, 1)

    def test_nan_is_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params(7, float("nan"), 1)

    def test_too_many_decimal_places(self) -> None:
        with self.assertRaises(SpirodrawError) as ctx:
            Params(7.1234, 2.5, 1)
        self.assertIn("3 位小数", str(ctx.exception))

    def test_turns_above_limit(self) -> None:
        with self.assertRaises(SpirodrawError) as ctx:
            Params(97, 89, 1)
        self.assertIn("闭合", str(ctx.exception))

    def test_degenerate_line_is_rejected(self) -> None:
        with self.assertRaises(SpirodrawError) as ctx:
            Params(6, 3, 3)
        self.assertIn("直线", str(ctx.exception))

    def test_radius_out_of_range(self) -> None:
        with self.assertRaises(SpirodrawError):
            Params(500, 3, 1)


class BoundsAndHelpersTest(unittest.TestCase):
    def test_bounds_contains_all_points(self) -> None:
        points = sample_points(Params(9, 6, 3), 24)
        box = bounds(points)
        for point in points:
            self.assertTrue(box.contains(point))
        self.assertGreater(box.width, 0)
        self.assertGreater(box.height, 0)

    def test_bounds_center(self) -> None:
        box = bounds([(0, 0), (4, 2)])
        self.assertEqual(box.center, (2.0, 1.0))

    def test_bounds_rejects_empty(self) -> None:
        with self.assertRaises(SpirodrawError):
            bounds([])

    def test_count_distinct(self) -> None:
        self.assertEqual(count_distinct([(0, 0), (1, 0), (2, 0), (1, 0)]), 3)

    def test_count_distinct_rejects_bad_tolerance(self) -> None:
        with self.assertRaises(SpirodrawError):
            count_distinct([(0, 0)], 0)

    def test_format_number(self) -> None:
        self.assertEqual(format_number(7.5), "7.5")
        self.assertEqual(format_number(3.0), "3")
        self.assertEqual(format_number(0), "0")
        self.assertEqual(format_number(2.125), "2.125")
        self.assertEqual(format_number(0.0001), "0.0001")
        self.assertEqual(format_number(12.500000), "12.5")

    def test_format_number_rejects_text(self) -> None:
        with self.assertRaises(SpirodrawError):
            format_number("1")  # type: ignore[arg-type]

    def test_visual_signature(self) -> None:
        params = Params(10, 4, 2)
        ratio, depth = visual_signature(params)
        self.assertAlmostEqual(ratio, 2.5)
        self.assertAlmostEqual(depth, 0.5)

    def test_scaled_curves_are_visually_equal(self) -> None:
        first = Params(10, 4, 2)
        second = Params(20, 8, 4)
        self.assertAlmostEqual(visual_distance(first, second), 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
