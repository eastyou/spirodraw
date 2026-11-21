"""参数生成单元测试：去重、视觉间距与随机种子复现。"""

from __future__ import annotations

import unittest

from spirodraw.model import (
    DEFAULT_SEED,
    MAX_CURVES,
    MIN_SELECTION_DISTANCE,
    Params,
    SpirodrawError,
    candidate_pool,
    generate_params,
    validate_selection,
    visual_distance,
    visual_signature,
)


class CandidatePoolTest(unittest.TestCase):
    def test_pool_has_enough_items(self) -> None:
        pool = candidate_pool()
        self.assertIsInstance(pool, tuple)
        self.assertGreaterEqual(len(pool), MAX_CURVES)

    def test_pool_items_are_valid(self) -> None:
        for params in candidate_pool():
            self.assertIsInstance(params, Params)
            self.assertGreater(params.R, params.r)
            self.assertGreater(params.d, 0)
            self.assertLessEqual(params.d, params.r)

    def test_pool_has_unique_visual_signatures(self) -> None:
        keys = set()
        for params in candidate_pool():
            ratio, depth = visual_signature(params)
            keys.add((round(ratio, 4), round(depth, 4)))
        self.assertEqual(len(keys), len(candidate_pool()))


class GenerateParamsTest(unittest.TestCase):
    def test_default_count_and_seed(self) -> None:
        self.assertEqual(generate_params(), generate_params(6, DEFAULT_SEED))

    def test_requested_count(self) -> None:
        for count in (1, 3, 6, 12):
            self.assertEqual(len(generate_params(count)), count)

    def test_same_seed_is_reproducible(self) -> None:
        self.assertEqual(generate_params(6, 7), generate_params(6, 7))

    def test_different_seeds_differ(self) -> None:
        self.assertNotEqual(generate_params(6, 1), generate_params(6, 2))

    def test_negative_seed_is_allowed(self) -> None:
        self.assertEqual(len(generate_params(2, -5)), 2)

    def test_params_are_exactly_unique(self) -> None:
        chosen = generate_params(12, 42)
        self.assertEqual(len(set(chosen)), 12)

    def test_params_are_visually_separated(self) -> None:
        chosen = generate_params(12, 42)
        for i in range(len(chosen)):
            for j in range(i + 1, len(chosen)):
                self.assertGreaterEqual(
                    visual_distance(chosen[i], chosen[j]),
                    MIN_SELECTION_DISTANCE - 1e-9,
                )

    def test_signatures_are_unique(self) -> None:
        chosen = generate_params(12, 99)
        keys = set()
        for params in chosen:
            ratio, depth = visual_signature(params)
            keys.add((round(ratio, 4), round(depth, 4)))
        self.assertEqual(len(keys), len(chosen))

    def test_turns_are_ordered(self) -> None:
        chosen = generate_params(8, 42)
        turns = [params.period_turns for params in chosen]
        self.assertEqual(turns, sorted(turns))

    def test_invalid_counts(self) -> None:
        for value in (0, 13, -1, True, 3.0, "6"):
            with self.assertRaises(SpirodrawError):
                generate_params(value)  # type: ignore[arg-type]

    def test_invalid_seed(self) -> None:
        for value in (True, 1.5, "42"):
            with self.assertRaises(SpirodrawError):
                generate_params(3, value)  # type: ignore[arg-type]


class ValidateSelectionTest(unittest.TestCase):
    def test_duplicate_params_are_rejected(self) -> None:
        params = Params(9, 6, 3)
        with self.assertRaises(SpirodrawError) as ctx:
            validate_selection((params, params))
        self.assertIn("重复", str(ctx.exception))

    def test_scaled_duplicate_is_rejected(self) -> None:
        first = Params(10, 4, 2)
        second = Params(20, 8, 4)
        with self.assertRaises(SpirodrawError) as ctx:
            validate_selection((first, second))
        self.assertIn("相似", str(ctx.exception))

    def test_too_few_items_are_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            validate_selection(())

    def test_too_many_items_are_rejected(self) -> None:
        params = Params(9, 6, 3)
        with self.assertRaises(SpirodrawError):
            validate_selection(tuple([params] * (MAX_CURVES + 1)))

    def test_non_params_item_is_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            validate_selection((Params(9, 6, 3), "x"))  # type: ignore[arg-type]

    def test_valid_selection_passes(self) -> None:
        validate_selection(generate_params(6, 42))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
