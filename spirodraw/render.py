"""把万花尺曲线渲染成 A4 纵向可打印的描摹画册。"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .model import (
    MAX_CURVES,
    MIN_CURVES,
    SAMPLES_PER_TURN,
    Params,
    SpirodrawError,
    format_number,
    sample_count,
    sample_points,
)

PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
CARDS_PER_PAGE = 2
VIEW_ASPECT = 1.38
VIEW_PADDING = 0.10
GUIDE_TITLE = "自制万花尺"
MAX_TITLE_LENGTH = 40

COLORS: Tuple[Tuple[str, str], ...] = (
    ("靛蓝", "#2743a6"),
    ("朱红", "#b3261e"),
    ("松绿", "#1c6b47"),
    ("紫罗兰", "#6b3fa0"),
    ("赭石", "#a15c12"),
    ("孔雀蓝", "#0f6f7a"),
    ("玫红", "#b02a5b"),
    ("橄榄", "#5c6b1f"),
    ("群青", "#3b3f8f"),
    ("品红", "#8e2a8a"),
    ("墨绿", "#205b50"),
    ("砖橙", "#b04a24"),
)


@dataclass(frozen=True)
class ViewBox:
    """SVG viewBox 的四个数值。"""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name, value in (
            ("x", self.x),
            ("y", self.y),
            ("width", self.width),
            ("height", self.height),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise SpirodrawError("viewBox 的 %s 必须是数字" % name)
            if not math.isfinite(float(value)):
                raise SpirodrawError("viewBox 的 %s 必须是有限数值" % name)
        if self.width <= 0 or self.height <= 0:
            raise SpirodrawError("viewBox 的宽高必须大于 0")

    @property
    def aspect(self) -> float:
        return self.width / self.height

    def contains(self, point: Tuple[float, float], tolerance: float = 0.0) -> bool:
        """判断点是否落在 viewBox 内（可给容差）。"""
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise SpirodrawError("点必须是 (x, y) 二元组")
        x, y = float(point[0]), float(point[1])
        if tolerance < 0:
            raise SpirodrawError("容差不能为负数")
        return (
            self.x - tolerance <= x <= self.x + self.width + tolerance
            and self.y - tolerance <= y <= self.y + self.height + tolerance
        )


def page_count(curve_count: int) -> int:
    """总页数：每页 2 条曲线，最后再加 1 页自制说明。"""
    if isinstance(curve_count, bool) or not isinstance(curve_count, int):
        raise SpirodrawError("曲线数量必须是整数")
    if not MIN_CURVES <= curve_count <= MAX_CURVES:
        raise SpirodrawError(
            "曲线数量必须在 %d~%d 之间，当前是 %d"
            % (MIN_CURVES, MAX_CURVES, curve_count)
        )
    return (curve_count + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE + 1


def to_svg_points(
    points: Sequence[Tuple[float, float]]
) -> List[Tuple[float, float]]:
    """把数学坐标（y 轴向上）翻成 SVG 坐标（y 轴向下）。"""
    if isinstance(points, (str, bytes)) or not isinstance(points, (list, tuple)):
        raise SpirodrawError("点集必须是列表或元组")
    if not points:
        raise SpirodrawError("点集不能为空")
    converted: List[Tuple[float, float]] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise SpirodrawError("点必须是 (x, y) 二元组")
        x = float(point[0])
        y = float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise SpirodrawError("坐标必须是有限数值")
        converted.append((x, -y))
    return converted


def fit_view_box(
    points: Sequence[Tuple[float, float]],
    aspect: float = VIEW_ASPECT,
    padding: float = VIEW_PADDING,
) -> ViewBox:
    """按点集包围盒生成固定宽高比的 viewBox，保证所有点完整可见。"""
    if isinstance(points, (str, bytes)) or not isinstance(points, (list, tuple)):
        raise SpirodrawError("点集必须是列表或元组")
    if not points:
        raise SpirodrawError("点集不能为空")
    if not isinstance(aspect, (int, float)) or isinstance(aspect, bool):
        raise SpirodrawError("宽高比必须是数字")
    if not math.isfinite(float(aspect)) or aspect <= 0:
        raise SpirodrawError("宽高比必须大于 0")
    if not isinstance(padding, (int, float)) or isinstance(padding, bool):
        raise SpirodrawError("留白比例必须是数字")
    if not math.isfinite(float(padding)) or padding < 0:
        raise SpirodrawError("留白比例不能为负数")

    xs: List[float] = []
    ys: List[float] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise SpirodrawError("点必须是 (x, y) 二元组")
        x = float(point[0])
        y = float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise SpirodrawError("坐标必须是有限数值")
        xs.append(x)
        ys.append(y)

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    content = max(span_x, span_y * float(aspect))
    width = content * (1.0 + 2.0 * float(padding))
    height = width / float(aspect)
    return ViewBox(center_x - width / 2.0, center_y - height / 2.0, width, height)


def path_data(points: Sequence[Tuple[float, float]]) -> str:
    """把点列转成闭合的 SVG path 数据。"""
    if isinstance(points, (str, bytes)) or not isinstance(points, (list, tuple)):
        raise SpirodrawError("点集必须是列表或元组")
    if not points:
        raise SpirodrawError("点集不能为空")
    coords: List[str] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise SpirodrawError("点必须是 (x, y) 二元组")
        x = float(point[0])
        y = float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise SpirodrawError("坐标必须是有限数值")
        coords.append("%.2f %.2f" % (x, y))
    return "M " + coords[0] + " L " + " L ".join(coords[1:]) + " Z"


def _color_for(index: int) -> Tuple[str, str]:
    return COLORS[index % len(COLORS)]


def _format_view_box(box: ViewBox) -> str:
    return "%.3f %.3f %.3f %.3f" % (box.x, box.y, box.width, box.height)


def svg_markup(
    params: Params, index: int, samples_per_turn: int = SAMPLES_PER_TURN
) -> str:
    """生成单条曲线的内联 SVG。"""
    if not isinstance(params, Params):
        raise SpirodrawError("params 必须是 Params 对象")
    if isinstance(index, bool) or not isinstance(index, int):
        raise SpirodrawError("曲线序号必须是整数")
    if index < 0:
        raise SpirodrawError("曲线序号不能为负数")

    points = to_svg_points(sample_points(params, samples_per_turn))
    box = fit_view_box(points)
    color = _color_for(index)[1]
    stroke = box.width * 0.0032
    label = "第 %d 条万花尺曲线，定圆半径 %s，动圆半径 %s，笔距 %s" % (
        index + 1,
        format_number(params.R),
        format_number(params.r),
        format_number(params.d),
    )
    return (
        '<svg viewBox="%s" role="img" aria-label="%s">'
        '<path d="%s" fill="none" stroke="%s" stroke-width="%.3f" '
        'stroke-linecap="round" stroke-linejoin="round"></path></svg>'
        % (
            _format_view_box(box),
            html.escape(label),
            path_data(points),
            color,
            stroke,
        )
    )


def card_markup(
    params: Params, index: int, samples_per_turn: int = SAMPLES_PER_TURN
) -> str:
    """生成一张曲线卡片：图形 + 参数表。"""
    if not isinstance(params, Params):
        raise SpirodrawError("params 必须是 Params 对象")
    color_name, color_hex = _color_for(index)
    depth_ratio = params.d / params.r
    return (
        '<article class="card">'
        '<div class="card-head"><h2>曲线 %02d</h2>'
        '<span class="turns">闭合 %d 圈</span></div>'
        '<div class="figure">%s</div>'
        '<table class="params"><tbody>'
        "<tr><th>定圆半径 R</th><td>%s</td><th>动圆半径 r</th><td>%s</td></tr>"
        "<tr><th>笔距 d</th><td>%s</td><th>闭合圈数</th><td>%d 圈</td></tr>"
        '<tr><th>笔距比 d/r</th><td>%s</td><th>颜色</th>'
        '<td><span class="swatch" style="background:%s"></span>%s</td></tr>'
        "</tbody></table>"
        "</article>"
        % (
            index + 1,
            params.period_turns,
            svg_markup(params, index, samples_per_turn),
            format_number(params.R),
            format_number(params.r),
            format_number(params.d),
            params.period_turns,
            "%.2f" % depth_ratio,
            color_hex,
            html.escape(color_name),
        )
    )


def _page_head(title: str, page_no: int, page_total: int) -> str:
    return (
        '<div class="sheet-head"><h1>%s</h1>'
        '<span class="page">第 %d 页 / 共 %d 页</span></div>'
        % (html.escape(title), page_no, page_total)
    )


def _cards_page(
    cards: Sequence[str], title: str, page_no: int, page_total: int
) -> str:
    return (
        '<section class="sheet">%s<div class="cards">%s</div></section>'
        % (_page_head(title, page_no, page_total), "".join(cards))
    )


def _guide_page(
    params_list: Sequence[Params], page_no: int, page_total: int
) -> str:
    rows: List[str] = []
    for index, params in enumerate(params_list):
        color_name, color_hex = _color_for(index)
        rows.append(
            "<tr><td>%02d</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td>"
            '<td><span class="swatch" style="background:%s"></span>%s</td></tr>'
            % (
                index + 1,
                format_number(params.R),
                format_number(params.r),
                format_number(params.d),
                params.period_turns,
                color_hex,
                html.escape(color_name),
            )
        )

    return (
        '<section class="sheet guide">'
        "%s"
        '<p class="lead">把参数抄到真实画板上即可复现：卡片上的 R、r、d '
        "保持相同比例，整体放大或缩小都不会改变图案。</p>"
        '<p class="formula">x(t) = (R − r)·cos t + d·cos((R − r)/r · t)<br>'
        "y(t) = (R − r)·sin t − d·sin((R − r)/r · t)</p>"
        '<ol class="steps">'
        "<li>找两块硬纸板，各剪一个圆：定圆半径 R，动圆半径 r。</li>"
        "<li>在动圆上量出笔距 d，扎一个小孔，刚好能插进笔尖。</li>"
        "<li>把定圆固定在纸上，动圆放进定圆内侧，让两圆内切。</li>"
        "<li>笔尖插入小孔，保持动圆始终贴着定圆内壁，慢慢滚动。</li>"
        "<li>表里的「闭合圈数」是动圆需要滚过的圈数；滚满这些圈，"
        "曲线正好回到起点。</li>"
        "<li>沿铅笔线用彩笔描摹，就得到和卡片上一模一样的图案。</li>"
        "</ol>"
        '<table class="all"><thead><tr><th>序号</th><th>定圆 R</th>'
        "<th>动圆 r</th><th>笔距 d</th><th>闭合圈数</th><th>颜色</th></tr></thead>"
        "<tbody>%s</tbody></table>"
        '<p class="note">小提示：纸下垫一张废纸，笔尖用力均匀；'
        "先轻描一遍，再用彩笔加粗，曲线会更顺滑。</p>"
        "</section>"
        % (
            _page_head(GUIDE_TITLE, page_no, page_total),
            "".join(rows),
        )
    )


def render_html(
    params_list: Sequence[Params],
    title: str = "万花尺描摹画册",
    samples_per_turn: int = SAMPLES_PER_TURN,
) -> str:
    """生成完整、自包含的 A4 描摹画册 HTML。"""
    if isinstance(params_list, (str, bytes)) or not isinstance(
        params_list, (list, tuple)
    ):
        raise SpirodrawError("参数组必须是列表或元组")
    if not MIN_CURVES <= len(params_list) <= MAX_CURVES:
        raise SpirodrawError(
            "参数组数量必须在 %d~%d 之间，当前是 %d"
            % (MIN_CURVES, MAX_CURVES, len(params_list))
        )
    for index, params in enumerate(params_list):
        if not isinstance(params, Params):
            raise SpirodrawError("第 %d 组参数不是 Params 对象" % (index + 1))
        sample_count(params, samples_per_turn)

    if not isinstance(title, str):
        raise SpirodrawError("标题必须是文本")
    cleaned_title = title.strip()
    if not cleaned_title:
        raise SpirodrawError("标题不能为空")
    if len(cleaned_title) > MAX_TITLE_LENGTH:
        raise SpirodrawError("标题最多 %d 个字符" % MAX_TITLE_LENGTH)

    total_pages = page_count(len(params_list))
    pages: List[str] = []
    for start in range(0, len(params_list), CARDS_PER_PAGE):
        chunk = params_list[start : start + CARDS_PER_PAGE]
        cards = [
            card_markup(params, start + offset, samples_per_turn)
            for offset, params in enumerate(chunk)
        ]
        pages.append(
            _cards_page(
                cards,
                cleaned_title,
                len(pages) + 1,
                total_pages,
            )
        )
    pages.append(_guide_page(params_list, total_pages, total_pages))

    toolbar = (
        '<header class="toolbar"><strong>%s</strong>'
        "<span>%d 条曲线 · %d 页 A4</span></header>"
        % (html.escape(cleaned_title), len(params_list), total_pages)
    )
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n"
        "%s\n<main>\n%s\n</main>\n</body>\n</html>\n"
        % (
            html.escape(cleaned_title),
            _style(),
            toolbar,
            "\n".join(pages),
        )
    )


def _style() -> str:
    return """
  :root {
    color-scheme: light;
    --ink: #0f172a;
    --line: #cbd5e1;
    --muted: #64748b;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: #dfe5ec;
    color: var(--ink);
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
      "Source Han Sans SC", sans-serif;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .toolbar {
    width: 210mm;
    max-width: 100%;
    margin: 0 auto;
    padding: 6mm 0 4mm;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    font-size: 12px;
    color: #475569;
  }
  .toolbar strong { font-size: 15px; letter-spacing: 2px; }
  .toolbar span { color: var(--muted); }
  main { padding-bottom: 8mm; }
  .sheet {
    position: relative;
    width: 210mm;
    height: 297mm;
    margin: 0 auto 7mm;
    padding: 12mm 12mm 10mm;
    background: #fff;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.16);
    display: flex;
    flex-direction: column;
    page-break-after: always;
    break-after: page;
    overflow: hidden;
  }
  .sheet:last-child { page-break-after: auto; break-after: auto; }
  .sheet-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    border-bottom: 0.4mm solid #e2e8f0;
    padding-bottom: 2.5mm;
    margin-bottom: 4mm;
  }
  .sheet-head h1 {
    margin: 0;
    font-size: 14pt;
    font-weight: 600;
    letter-spacing: 3pt;
  }
  .sheet-head .page { font-size: 9pt; color: var(--muted); white-space: nowrap; }
  .cards {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-rows: repeat(2, minmax(0, 1fr));
    gap: 6mm;
  }
  .card {
    border: 0.3mm solid var(--line);
    border-radius: 2.5mm;
    padding: 4mm 5mm 3.5mm;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .card-head {
    display: flex;
    align-items: baseline;
    gap: 2mm;
    margin-bottom: 1mm;
  }
  .card-head h2 {
    margin: 0;
    flex: 1;
    font-size: 11pt;
    font-weight: 600;
    letter-spacing: 1pt;
  }
  .card-head .turns { font-size: 9pt; color: var(--muted); }
  .figure {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .figure svg { width: 100%; height: 100%; display: block; }
  table.params {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    font-size: 8.5pt;
  }
  table.params th,
  table.params td {
    border-top: 0.2mm solid #e2e8f0;
    padding: 1.2mm 1mm;
    text-align: left;
  }
  table.params th { width: 22%; color: var(--muted); font-weight: 500; }
  table.params td { width: 28%; font-variant-numeric: tabular-nums; }
  .swatch {
    display: inline-block;
    width: 3mm;
    height: 3mm;
    margin-right: 1.5mm;
    border-radius: 50%;
    vertical-align: -0.5mm;
  }
  .guide .lead { margin: 0 0 3mm; font-size: 10.5pt; color: #334155; }
  .guide .formula {
    margin: 0 0 4mm;
    padding: 3mm 4mm;
    background: #f8fafc;
    border-left: 1mm solid #94a3b8;
    font-size: 10pt;
    line-height: 1.7;
    font-variant-numeric: tabular-nums;
  }
  .guide .steps {
    margin: 0 0 4mm;
    padding-left: 6mm;
    font-size: 9.5pt;
    line-height: 1.65;
  }
  .guide .steps li { margin-bottom: 1mm; }
  table.all {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    table-layout: fixed;
  }
  table.all th,
  table.all td {
    border: 0.2mm solid var(--line);
    padding: 1.4mm 1mm;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  table.all th { background: #f1f5f9; font-weight: 600; }
  .guide .note {
    margin: 4mm 0 0;
    font-size: 8.5pt;
    color: var(--muted);
  }
  @media screen and (max-width: 820px) {
    body { background: #fff; }
    .toolbar { width: 100%; padding: 4mm 4mm 2mm; }
    .sheet {
      width: 100%;
      height: auto;
      margin: 0 0 4mm;
      padding: 5mm 4mm;
      box-shadow: none;
      overflow: visible;
    }
    .cards { grid-template-rows: none; grid-auto-rows: auto; }
    .card { padding: 3mm; }
    .figure { height: 62vw; min-height: 48vw; }
    .sheet-head h1 { font-size: 12pt; letter-spacing: 1.5pt; }
  }
  @page { size: A4 portrait; margin: 0; }
  @media print {
    body { background: #fff; }
    .toolbar { display: none; }
    main { padding: 0; }
    .sheet { margin: 0; box-shadow: none; }
    .sheet:last-child { page-break-after: auto; break-after: auto; }
  }
"""
