"""万花尺（内摆线 hypotrochoid）的参数、闭合周期与采样。"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from typing import List, Sequence, Tuple, Union

Number = Union[int, float]

MIN_CURVES = 1
MAX_CURVES = 12
DEFAULT_SEED = 42
SAMPLES_PER_TURN = 180
MIN_SAMPLES_PER_TURN = 12
MAX_SAMPLES_PER_TURN = 720
MAX_POINTS = 4000
MAX_TURNS = 20
MAX_DECIMAL_PLACES = 3
MIN_RADIUS = 1.0
MAX_RADIUS = 200.0
MIN_DISTINCT_POINTS = 3
POINT_TOLERANCE = 1e-9
MIN_SELECTION_DISTANCE = 0.06


class SpirodrawError(ValueError):
    """万花尺参数或外部输入不合法。"""


def format_number(value: Number) -> str:
    """把数字格式化成最多 6 位小数、去掉尾随零的文本。"""
    number = _require_number("数值", value)
    if number == 0:
        return "0"
    text = ("%.6f" % number).rstrip("0").rstrip(".")
    return text


def _require_number(name: str, value: Number) -> float:
    """校验数字类型与有限性，返回 float。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpirodrawError("参数 %s 必须是数字" % name)
    number = float(value)
    if not math.isfinite(number):
        raise SpirodrawError("参数 %s 必须是有限数值" % name)
    return number


def _decimal_units(first: float, second: float) -> Tuple[int, int]:
    """把两个有限小数按共同倍率放大成整数，用于精确求最大公约数。"""
    try:
        a = Decimal(str(first)).normalize()
        b = Decimal(str(second)).normalize()
    except InvalidOperation as exc:
        raise SpirodrawError("半径必须是有限小数") from exc

    places = 0
    for label, value in (("R", a), ("r", b)):
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int):
            raise SpirodrawError("参数 %s 必须是有限数值" % label)
        places = max(places, -exponent)
    if places > MAX_DECIMAL_PLACES:
        raise SpirodrawError(
            "半径 R 与 r 最多支持 %d 位小数，当前有 %d 位"
            % (MAX_DECIMAL_PLACES, places)
        )
    factor = Decimal(10) ** places
    return (
        int((a * factor).to_integral_value(rounding=ROUND_HALF_UP)),
        int((b * factor).to_integral_value(rounding=ROUND_HALF_UP)),
    )


@dataclass(frozen=True)
class Params:
    """一组万花尺参数：定圆半径 R、动圆半径 r、笔距 d。"""

    R: float
    r: float
    d: float

    def __post_init__(self) -> None:
        R = _require_number("R", self.R)
        r = _require_number("r", self.r)
        d = _require_number("d", self.d)

        if not MIN_RADIUS <= R <= MAX_RADIUS:
            raise SpirodrawError(
                "定圆半径 R 必须在 %s~%s 之间，当前是 %s"
                % (format_number(MIN_RADIUS), format_number(MAX_RADIUS), format_number(R))
            )
        if not MIN_RADIUS <= r <= MAX_RADIUS:
            raise SpirodrawError(
                "动圆半径 r 必须在 %s~%s 之间，当前是 %s"
                % (format_number(MIN_RADIUS), format_number(MAX_RADIUS), format_number(r))
            )
        if R <= r:
            raise SpirodrawError(
                "定圆半径 R 必须大于动圆半径 r（当前 R=%s，r=%s）"
                % (format_number(R), format_number(r))
            )
        if d <= 0:
            raise SpirodrawError("笔距 d 必须大于 0")
        if d > r:
            raise SpirodrawError(
                "笔距 d 不能大于动圆半径 r（当前 d=%s，r=%s）"
                % (format_number(d), format_number(r))
            )
        if R == 2 * r and abs(d - r) <= POINT_TOLERANCE:
            raise SpirodrawError("曲线退化成直线：R 是 r 的两倍且 d 等于 r，请调整参数")

        object.__setattr__(self, "R", R)
        object.__setattr__(self, "r", r)
        object.__setattr__(self, "d", d)

        self._validate_closure()
        self._validate_points()

    @property
    def period_turns(self) -> int:
        """动圆需要滚过的圈数（r / gcd(R, r)），也是闭合所需的周期数。"""
        R_units, r_units = _decimal_units(self.R, self.r)
        divisor = math.gcd(R_units, r_units)
        if divisor <= 0:
            raise SpirodrawError("无法计算闭合周期，请检查 R 与 r")
        turns = r_units // divisor
        if turns > MAX_TURNS:
            raise SpirodrawError(
                "曲线需要 %d 圈才能闭合，超过上限 %d 圈，请调整 R 或 r"
                % (turns, MAX_TURNS)
            )
        return turns

    @property
    def rotation_ratio(self) -> float:
        """笔尖相对动圆转动的角速度倍率 (R - r) / r。"""
        return (self.R - self.r) / self.r

    def _validate_closure(self) -> None:
        turns = self.period_turns
        if turns < 1:
            raise SpirodrawError("曲线无法闭合，请调整 R 或 r")

    def _validate_points(self) -> None:
        points = sample_points(self, samples_per_turn=MIN_SAMPLES_PER_TURN)
        if count_distinct(points) < MIN_DISTINCT_POINTS:
            raise SpirodrawError("曲线退化成点，请调整 R、r 或 d")


@dataclass(frozen=True)
class Bounds:
    """二维点集的轴对齐包围盒。"""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def contains(self, point: Tuple[float, float], tolerance: float = 0.0) -> bool:
        """判断点是否在包围盒内（可给容差）。"""
        x, y = _require_point(point)
        if tolerance < 0:
            raise SpirodrawError("容差不能为负数")
        return (
            self.min_x - tolerance <= x <= self.max_x + tolerance
            and self.min_y - tolerance <= y <= self.max_y + tolerance
        )


def _require_point(point: Tuple[float, float]) -> Tuple[float, float]:
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        raise SpirodrawError("点必须是 (x, y) 二元组")
    x = _require_number("x", point[0])
    y = _require_number("y", point[1])
    return x, y


def _require_points(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if isinstance(points, (str, bytes)) or not isinstance(points, (list, tuple)):
        raise SpirodrawError("点集必须是列表或元组")
    if not points:
        raise SpirodrawError("点集不能为空")
    cleaned: List[Tuple[float, float]] = []
    for point in points:
        cleaned.append(_require_point(point))
    return cleaned


def _validate_samples(samples_per_turn: int) -> int:
    if isinstance(samples_per_turn, bool) or not isinstance(samples_per_turn, int):
        raise SpirodrawError("每圈采样数必须是整数")
    if not MIN_SAMPLES_PER_TURN <= samples_per_turn <= MAX_SAMPLES_PER_TURN:
        raise SpirodrawError(
            "每圈采样数必须在 %d~%d 之间，当前是 %d"
            % (MIN_SAMPLES_PER_TURN, MAX_SAMPLES_PER_TURN, samples_per_turn)
        )
    return samples_per_turn


def point_at(params: Params, t: Number) -> Tuple[float, float]:
    """按参数方程计算 t 时刻的笔尖坐标。"""
    if not isinstance(params, Params):
        raise SpirodrawError("params 必须是 Params 对象")
    angle = _require_number("t", t)
    ratio = params.rotation_ratio
    x = (params.R - params.r) * math.cos(angle) + params.d * math.cos(ratio * angle)
    y = (params.R - params.r) * math.sin(angle) - params.d * math.sin(ratio * angle)
    return (x, y)


def sample_count(params: Params, samples_per_turn: int = SAMPLES_PER_TURN) -> int:
    """曲线采样点总数：周期圈数 × 每圈采样数 + 1（末点回到首点）。"""
    if not isinstance(params, Params):
        raise SpirodrawError("params 必须是 Params 对象")
    per_turn = _validate_samples(samples_per_turn)
    total = params.period_turns * per_turn
    if total + 1 > MAX_POINTS:
        raise SpirodrawError(
            "采样点过多：%d 个，上限 %d 个，请减少每圈采样数"
            % (total + 1, MAX_POINTS)
        )
    return total + 1


def sample_points(
    params: Params, samples_per_turn: int = SAMPLES_PER_TURN
) -> List[Tuple[float, float]]:
    """等角度采样整条闭合曲线，末点与首点完全相同。"""
    count = sample_count(params, samples_per_turn)
    step = 2.0 * math.pi / samples_per_turn
    points: List[Tuple[float, float]] = []
    for index in range(count - 1):
        points.append(point_at(params, index * step))
    points.append(points[0])
    return points


def count_distinct(
    points: Sequence[Tuple[float, float]], tolerance: float = POINT_TOLERANCE
) -> int:
    """按给定容差量化后统计不同点的数量。"""
    cleaned = _require_points(points)
    if tolerance <= 0:
        raise SpirodrawError("去重容差必须大于 0")
    keys = set()
    for x, y in cleaned:
        keys.add((int(round(x / tolerance)), int(round(y / tolerance))))
    return len(keys)


def bounds(points: Sequence[Tuple[float, float]]) -> Bounds:
    """计算点集的包围盒。"""
    cleaned = _require_points(points)
    xs = [point[0] for point in cleaned]
    ys = [point[1] for point in cleaned]
    return Bounds(min(xs), min(ys), max(xs), max(ys))


def visual_signature(params: Params) -> Tuple[float, float]:
    """决定曲线视觉形状的两个比值：R/r 与 d/r。"""
    if not isinstance(params, Params):
        raise SpirodrawError("params 必须是 Params 对象")
    return (params.R / params.r, params.d / params.r)


def visual_distance(first: Params, second: Params) -> float:
    """两条曲线在「R/r, d/r」参数平面上的距离，用于避免视觉重复。"""
    a_ratio, a_depth = visual_signature(first)
    b_ratio, b_depth = visual_signature(second)
    return math.hypot(a_ratio - b_ratio, a_depth - b_depth)


def validate_selection(
    params_list: Sequence[Params], min_distance: float = MIN_SELECTION_DISTANCE
) -> None:
    """校验一组参数：数量合法、完全重复与视觉近似重复都要拒绝。"""
    if isinstance(params_list, (str, bytes)) or not isinstance(params_list, (list, tuple)):
        raise SpirodrawError("参数组必须是列表或元组")
    if not MIN_CURVES <= len(params_list) <= MAX_CURVES:
        raise SpirodrawError(
            "参数组数量必须在 %d~%d 之间" % (MIN_CURVES, MAX_CURVES)
        )
    if min_distance < 0:
        raise SpirodrawError("最小视觉距离不能为负数")

    seen: List[Tuple[float, float, float]] = []
    for index, item in enumerate(params_list):
        if not isinstance(item, Params):
            raise SpirodrawError("第 %d 组参数不是 Params 对象" % (index + 1))
        key = (item.R, item.r, item.d)
        if key in seen:
            raise SpirodrawError("第 %d 组参数与前面的曲线完全重复" % (index + 1))
        seen.append(key)

    for i in range(len(params_list)):
        for j in range(i + 1, len(params_list)):
            if visual_distance(params_list[i], params_list[j]) < min_distance:
                raise SpirodrawError(
                    "第 %d 条与第 %d 条曲线过于相似，描摹时会分不清"
                    % (i + 1, j + 1)
                )


def _validate_count(count: int) -> int:
    if isinstance(count, bool) or not isinstance(count, int):
        raise SpirodrawError("曲线数量必须是整数")
    if not MIN_CURVES <= count <= MAX_CURVES:
        raise SpirodrawError(
            "曲线数量必须在 %d~%d 之间，当前是 %d" % (MIN_CURVES, MAX_CURVES, count)
        )
    return count


def _validate_seed(seed: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SpirodrawError("随机种子必须是整数")
    return seed


@lru_cache(maxsize=1)
def candidate_pool() -> Tuple[Params, ...]:
    """内置候选参数池：比例各异、闭合圈数适中的曲线。"""
    ratios = (0.35, 0.5, 0.7, 0.9, 1.0)
    seen = set()
    items: List[Params] = []
    for R in range(7, 41):
        for r in range(2, (R - 1) // 2 + 1):
            for depth in ratios:
                d = round(r * depth, 2)
                if d <= 0 or d > r:
                    continue
                try:
                    params = Params(float(R), float(r), d)
                except SpirodrawError:
                    continue
                if params.period_turns > 12:
                    continue
                signature = visual_signature(params)
                key = (round(signature[0], 4), round(signature[1], 4))
                if key in seen:
                    continue
                seen.add(key)
                items.append(params)
    items.sort(key=lambda item: (item.period_turns, item.R, item.r, item.d))
    return tuple(items)


def _pick_spaced(pool: Sequence[Params], count: int) -> Tuple[Params, ...]:
    """按视觉距离从池中贪心挑选，尽量让每条曲线都容易分辨。"""
    for threshold in (0.30, 0.24, 0.18, 0.12, MIN_SELECTION_DISTANCE):
        chosen: List[Params] = []
        for candidate in pool:
            if all(
                visual_distance(candidate, picked) >= threshold for picked in chosen
            ):
                chosen.append(candidate)
                if len(chosen) == count:
                    return tuple(chosen)
    raise SpirodrawError(
        "内置参数池无法选出 %d 组互不相似的曲线，请减少曲线数量" % count
    )


def generate_params(count: int = 6, seed: int = DEFAULT_SEED) -> Tuple[Params, ...]:
    """用指定种子从候选池挑选 count 组参数，同种子结果完全一致。"""
    _validate_count(count)
    _validate_seed(seed)
    pool = list(candidate_pool())
    if len(pool) < count:
        raise SpirodrawError("内置参数池数量不足，请减少曲线数量")

    random.Random(seed).shuffle(pool)
    chosen = _pick_spaced(pool, count)
    ordered = tuple(sorted(chosen, key=lambda item: (item.period_turns, item.R, item.r)))
    validate_selection(ordered)
    return ordered
