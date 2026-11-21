"""render 模块单元测试：页面布局、SVG 边界、转义与打印样式。"""

from __future__ import annotations

import re
import unittest

from spirodraw.model import (
    MAX_CURVES,
    SAMPLES_PER_TURN,
    Params,
    SpirodrawError,
    format_number,
    generate_params,
    sample_count,
    sample_points,
)
from spirodraw.render import (
    GUIDE_TITLE,
    VIEW_ASPECT,
    fit_view_box,
    page_count,
    path_data,
    render_html,
    to_svg_points,
)

PATH_PATTERN = re.compile(r'<path d="([^"]+)"')
VIEWBOX_PATTERN = re.compile(r'viewBox="([^"]+)"')
STROKE_PATTERN = re.compile(r'stroke="(#[0-9a-f]{6})"')


class PageCountTest(unittest.TestCase):
    def test_page_count(self) -> None:
        self.assertEqual(page_count(1), 2)
        self.assertEqual(page_count(2), 2)
        self.assertEqual(page_count(3), 3)
        self.assertEqual(page_count(6), 4)
        self.assertEqual(page_count(12), 7)

    def test_invalid_page_count(self) -> None:
        for value in (0, 13, -1, True, "6"):
            with self.assertRaises(SpirodrawError):
                page_count(value)  # type: ignore[arg-type]


class GeometryTest(unittest.TestCase):
    def test_svg_points_flip_y(self) -> None:
        self.assertEqual(to_svg_points([(1.0, 2.0), (-3.0, 0.5)]), [(1.0, -2.0), (-3.0, -0.5)])

    def test_view_box_contains_every_point(self) -> None:
        params = Params(9, 6, 3)
        points = to_svg_points(sample_points(params))
        box = fit_view_box(points)
        for x, y in points:
            self.assertTrue(box.contains((x, y), tolerance=1e-9))

    def test_view_box_has_requested_aspect(self) -> None:
        points = to_svg_points(sample_points(Params(9, 6, 3)))
        box = fit_view_box(points)
        self.assertAlmostEqual(box.aspect, VIEW_ASPECT, places=9)

    def test_view_box_adds_padding(self) -> None:
        points = [(0.0, 0.0), (10.0, 5.0)]
        box = fit_view_box(points)
        for x, y in points:
            self.assertGreater(x, box.x)
            self.assertLess(x, box.x + box.width)
            self.assertGreater(y, box.y)
            self.assertLess(y, box.y + box.height)

    def test_view_box_rejects_empty(self) -> None:
        with self.assertRaises(SpirodrawError):
            fit_view_box([])

    def test_view_box_rejects_bad_aspect(self) -> None:
        with self.assertRaises(SpirodrawError):
            fit_view_box([(0.0, 0.0)], aspect=0)

    def test_view_box_rejects_negative_padding(self) -> None:
        with self.assertRaises(SpirodrawError):
            fit_view_box([(0.0, 0.0)], padding=-0.1)

    def test_path_data_is_closed(self) -> None:
        data = path_data([(0, 0), (1, 1), (2, 0)])
        self.assertTrue(data.startswith("M 0.00 0.00"))
        self.assertTrue(data.endswith(" Z"))
        self.assertEqual(data.count(" L "), 2)

    def test_path_point_count_matches_samples(self) -> None:
        params = Params(9, 6, 3)
        points = to_svg_points(sample_points(params, 30))
        self.assertEqual(path_data(points).count(" L ") + 1, len(points))
        self.assertEqual(len(points), sample_count(params, 30))

    def test_path_data_rejects_empty(self) -> None:
        with self.assertRaises(SpirodrawError):
            path_data([])


class RenderHtmlTest(unittest.TestCase):
    def test_counts_for_six_curves(self) -> None:
        chosen = generate_params(6, 42)
        page = render_html(chosen)
        self.assertEqual(page.count("<article"), 6)
        self.assertEqual(page.count("<svg"), 6)
        self.assertEqual(page.count("<section class="), 4)
        self.assertEqual(len(STROKE_PATTERN.findall(page)), 6)

    def test_counts_for_twelve_curves(self) -> None:
        page = render_html(generate_params(12, 42))
        self.assertEqual(page.count("<article"), 12)
        self.assertEqual(page.count("<section class="), 7)

    def test_view_boxes_contain_their_curves(self) -> None:
        chosen = generate_params(6, 7)
        page = render_html(chosen)
        boxes = VIEWBOX_PATTERN.findall(page)
        self.assertEqual(len(boxes), 6)
        for params, raw in zip(chosen, boxes):
            x, y, width, height = [float(item) for item in raw.split()]
            points = to_svg_points(sample_points(params))
            for px, py in points:
                self.assertGreaterEqual(px, x - 1e-6)
                self.assertLessEqual(px, x + width + 1e-6)
                self.assertGreaterEqual(py, y - 1e-6)
                self.assertLessEqual(py, y + height + 1e-6)

    def test_path_commands_match_sample_count(self) -> None:
        params = Params(9, 6, 3)
        page = render_html([params])
        data = PATH_PATTERN.search(page)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data.group(1).count(" L ") + 1, sample_count(params))

    def test_colors_are_distinct(self) -> None:
        page = render_html(generate_params(6, 42))
        colors = STROKE_PATTERN.findall(page)
        self.assertEqual(len(set(colors)), 6)

    def test_parameter_text_is_present(self) -> None:
        page = render_html([Params(8, 3, 2)])
        self.assertIn("<th>定圆半径 R</th><td>8</td>", page)
        self.assertIn("<th>动圆半径 r</th><td>3</td>", page)
        self.assertIn("<th>笔距 d</th><td>2</td>", page)
        self.assertIn("<td>3 圈</td>", page)
        self.assertIn("闭合 3 圈", page)

    def test_guide_page_is_last(self) -> None:
        page = render_html(generate_params(3, 42))
        last = page.rsplit("<section class=", 1)[1]
        self.assertIn("sheet guide", last)
        self.assertIn(GUIDE_TITLE, last)
        self.assertIn("把参数抄到真实画板上即可复现", last)
        self.assertIn("闭合圈数", last)

    def test_guide_lists_all_radii(self) -> None:
        chosen = generate_params(3, 42)
        page = render_html(chosen)
        for params in chosen:
            self.assertIn(">%s<" % format_number(params.R), page)
            self.assertIn(">%s<" % format_number(params.r), page)
            self.assertIn(">%s<" % format_number(params.d), page)

    def test_each_card_contains_one_svg(self) -> None:
        page = render_html(generate_params(6, 42))
        cards = page.split("<article")[1:]
        self.assertEqual(len(cards), 6)
        for card in cards:
            self.assertEqual(card.count("<svg"), 1)
            self.assertEqual(card.count("<path"), 1)

    def test_cards_per_page_limit(self) -> None:
        page = render_html(generate_params(6, 42))
        sheets = page.split("<section class=")[1:]
        for sheet in sheets:
            self.assertLessEqual(sheet.count("<article"), 2)

    def test_print_and_screen_styles(self) -> None:
        page = render_html(generate_params(2, 42))
        self.assertIn("A4 portrait", page)
        self.assertIn("@page", page)
        self.assertIn("@media print", page)
        self.assertIn("max-width: 820px", page)
        self.assertIn("viewport", page)

    def test_no_external_resources(self) -> None:
        page = render_html(generate_params(3, 42))
        self.assertNotIn("http", page.lower())
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("src=", page.lower())
        self.assertNotIn("@import", page.lower())

    def test_title_is_escaped(self) -> None:
        page = render_html([Params(8, 3, 2)], title="<b>A&B</b>")
        self.assertNotIn("<b>A&B</b>", page)
        self.assertIn("&lt;b&gt;A&amp;B&lt;/b&gt;", page)

    def test_title_is_trimmed(self) -> None:
        page = render_html([Params(8, 3, 2)], title="  我的画册  ")
        self.assertIn("<h1>我的画册</h1>", page)

    def test_invalid_title(self) -> None:
        for title in ("", "   ", 3, "标" * 41):
            with self.assertRaises(SpirodrawError):
                render_html([Params(8, 3, 2)], title=title)  # type: ignore[arg-type]

    def test_empty_params_are_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            render_html([])

    def test_text_params_are_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            render_html("abc")  # type: ignore[arg-type]

    def test_too_many_params_are_rejected(self) -> None:
        chosen = list(generate_params(MAX_CURVES, 42))
        chosen.append(Params(8, 3, 2))
        with self.assertRaises(SpirodrawError):
            render_html(chosen)

    def test_non_params_item_is_rejected(self) -> None:
        with self.assertRaises(SpirodrawError):
            render_html([Params(8, 3, 2), "x"])  # type: ignore[list-item]

    def test_invalid_samples_are_rejected(self) -> None:
        for value in (0, 721, True):
            with self.assertRaises(SpirodrawError):
                render_html([Params(8, 3, 2)], samples_per_turn=value)  # type: ignore[arg-type]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
