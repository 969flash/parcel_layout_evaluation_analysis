from __future__ import annotations

import math
from typing import Dict, List, Tuple
import Rhino.Geometry as geo
from units import Block
import utils
import os


LOT_WEIGHT = 0.5
BLOCK_WEIGHT = 0.5

MIN_HULL_SAMPLE_POINTS = 200
MAX_HULL_SAMPLE_STEP = 1.0
MIN_HULL_SAMPLE_STEP = 1e-3

SHAPE_COMPONENT_WEIGHTS = {
    "convexity": 0.3,
    "circularity": 0.3,
    "squareness": 0.4,
}


def _is_debug_enabled() -> bool:
    flag = os.getenv("DEBUG_SHAPE_SCORES", "")
    return flag.lower() in {"1", "true", "yes", "on"}


def _log_debug(message: str) -> None:
    if _is_debug_enabled():
        print(f"[SHAPE DEBUG] {message}")


def compute(block: Block) -> float:
    """
    블록의 RSI(Revised Shape Index) 점수 계산.

    RSI = (w1 × Score_convexity + w2 × Score_circularity)

    - Score_convexity: 볼록성 점수 (0~1), 자루형/부정형 필지에 페널티
    - Score_circularity: 원형성 점수 (0~1), 극단적으로 길쭉한 필지에 페널티
    - w1, w2: 가중치 (각각 0.5)

    블록 내 모든 필지의 RSI 점수 평균을 반환합니다.
    """
    if not block.lots:
        return 0.0

    # 각 필지의 RSI 점수 계산
    lot_rsi_scores = []
    for lot in block.lots:
        region = getattr(lot, "region", None)
        if not region:
            continue
        lot_components = _compute_shape_components(region)
        rsi = _combine_components(lot_components)
        lot_rsi_scores.append(rsi)
        _log_debug(
            "Lot RSI -> convexity={:.3f}, circularity={:.3f}, squareness={:.3f}, rsi={:.3f}".format(
                lot_components["convexity"],
                lot_components["circularity"],
                lot_components["squareness"],
                rsi,
            )
        )

    lot_average = sum(lot_rsi_scores) / len(lot_rsi_scores) if lot_rsi_scores else None

    block_rsi = None
    block_region = getattr(block, "region", None)
    if block_region:
        block_components = _compute_shape_components(block_region)
        block_rsi = _combine_components(block_components)
        _log_debug(
            "Block RSI -> convexity={:.3f}, circularity={:.3f}, squareness={:.3f}, rsi={:.3f}".format(
                block_components["convexity"],
                block_components["circularity"],
                block_components["squareness"],
                block_rsi,
            )
        )

    weighted_components: List[Tuple[float, float]] = []
    if lot_average is not None:
        weighted_components.append((lot_average, LOT_WEIGHT))
    if block_rsi is not None:
        weighted_components.append((block_rsi, BLOCK_WEIGHT))

    if not weighted_components:
        return 0.0

    total_weight = sum(weight for _, weight in weighted_components)
    final_score = (
        sum(value * weight for value, weight in weighted_components) / total_weight
    )

    return max(0.0, min(1.0, final_score))


def _compute_shape_components(region: geo.Curve) -> Dict[str, float]:
    return {
        "convexity": get_convexity_index(region),
        "circularity": get_circularity_index(region),
        "squareness": get_squareness_index(region),
    }


def get_sq_shape_index(region: geo.Curve) -> float:
    """
    정사각형 기준 형태지수(SI) 계산: P / (4 * sqrt(A))

    - 정사각형: 1
    - 원: ~0.886 (정사각형보다 작음)
    - 길쭉/복잡: 1보다 큰 값으로 증가
    """
    area = float(utils.get_area(region))
    perim = float(region.GetLength())

    if area <= 0.0 or perim <= 0.0:
        return 0.0

    return perim / (6.0 * math.sqrt(area))


def get_convexity_index(region: geo.Curve) -> float:
    """
    볼록성 지수(CI) 계산: A / A_ch

    - A: 원래 영역 면적
    - A_ch: 최소 볼록 다각형(Convex Hull) 면적
    - 결과값은 (0, 1] 범위. 1에 가까울수록 더 볼록함.
    - 자루형, ㄷ자형, 별 모양 등 움푹 파인 필지에 페널티 부여
    """
    if not region or not getattr(region, "IsClosed", False):
        return 0.0

    try:
        area = float(utils.get_area(region))
    except Exception:
        return 0.0
    if area <= 0.0:
        return 0.0

    hull_crv = _convex_hull_curve(region)
    if not hull_crv:
        return 0.0
    try:
        hull_area = float(utils.get_area(hull_crv))
    except Exception:
        return 0.0
    if hull_area <= 0.0:
        return 0.0
    return area / hull_area


def get_circularity_index(region: geo.Curve) -> float:
    """
    원형성 지수(Isoperimetric Quotient) 계산: (4 × π × A) / P²

    - A: 필지 면적
    - P: 필지 둘레
    - 완벽한 원: 1.0
    - 정사각형: ~0.785
    - 길고 얇은 직사각형: 0에 가까운 값
    - 극단적으로 길쭉한 필지에 페널티 부여
    """
    if not region or not getattr(region, "IsClosed", False):
        return 0.0

    try:
        area = float(utils.get_area(region))
        perim = float(region.GetLength())
    except Exception:
        return 0.0

    if area <= 0.0 or perim <= 0.0:
        return 0.0

    # Isoperimetric Quotient 공식
    circularity = (4.0 * math.pi * area) / (perim * perim)

    # 이론적으로 1.0을 초과할 수 없지만, 부동소수점 오차로 인해 약간 초과할 수 있음
    return min(circularity, 1.0)


def get_squareness_index(region: geo.Curve) -> float:
    """정사각형에 가까울수록 높은 점수를 반환."""
    if not region or not getattr(region, "IsClosed", False):
        return 0.0

    try:
        bbox = region.GetBoundingBox(True)
    except Exception:
        return 0.0

    if not bbox or not bbox.IsValid:
        return 0.0

    width = max(bbox.Max.X - bbox.Min.X, 0.0)
    height = max(bbox.Max.Y - bbox.Min.Y, 0.0)

    if width <= 0.0 or height <= 0.0:
        return 0.0

    aspect_ratio = min(width, height) / max(width, height)

    vertex_count = _get_polygon_vertex_count(region)
    vertex_penalty = 1.0
    if vertex_count == 3:
        vertex_penalty = 0.5
    elif vertex_count == 4:
        vertex_penalty = 1.0
    elif vertex_count == 5:
        vertex_penalty = 0.9
    elif vertex_count == 6:
        vertex_penalty = 0.8
    elif vertex_count > 6:
        vertex_penalty = 0.7

    squareness = aspect_ratio * vertex_penalty
    return max(0.0, min(1.0, squareness))


def _convex_hull_curve(region: geo.Curve) -> geo.Curve | None:
    """
    주어진 닫힌 커브의 평면(월드 XY 가정)에서 2D Convex Hull을 계산해 PolylineCurve로 반환.
    샘플 포인트는 커브 분해 정점 + 균등 분할점 사용.
    """
    pts = _collect_hull_samples(region)
    if not pts:
        return None

    # 중복 제거 및 2D 투영 (XY 평면)
    unique = []
    seen = set()
    for p in pts:
        key = (round(p.X, 6), round(p.Y, 6))
        if key in seen:
            continue
        seen.add(key)
        unique.append(geo.Point3d(p.X, p.Y, 0.0))

    if len(unique) < 3:
        return None

    hull_pts = _monotone_chain(unique)
    if len(hull_pts) < 3:
        return None

    # 닫힌 폴리라인 커브 생성
    if hull_pts[0] != hull_pts[-1]:
        hull_pts.append(hull_pts[0])
    pl = geo.Polyline(hull_pts)
    if not pl.IsValid or not pl.IsClosed:
        return None
    return geo.PolylineCurve(pl)


def _collect_hull_samples(region: geo.Curve) -> List[geo.Point3d]:
    pts: List[geo.Point3d] = []

    try:
        success, polyline = region.TryGetPolyline()
        if success and polyline and len(polyline) > 0:
            pts.extend(polyline)
    except Exception:
        pass

    try:
        verts = utils.get_vertices(region)
        pts.extend(verts)
    except Exception:
        pass

    try:
        segments = region.DuplicateSegments()
        for seg in segments or []:
            pts.extend(utils.get_vertices(seg))
    except Exception:
        pass

    try:
        perim = max(region.GetLength(), 1e-6)
        step = max(
            min(perim / float(MIN_HULL_SAMPLE_POINTS), MAX_HULL_SAMPLE_STEP),
            MIN_HULL_SAMPLE_STEP,
        )
        dense_pts = utils.get_pts_by_length(region, step, include_start=True)
        pts.extend(dense_pts)
    except Exception:
        pass

    return pts


def _combine_components(components: Dict[str, float]) -> float:
    weighted: List[Tuple[float, float]] = []
    for key, value in components.items():
        weight = SHAPE_COMPONENT_WEIGHTS.get(key)
        if weight is None:
            continue
        if value is None:
            continue
        weighted.append((value, weight))

    if not weighted:
        return 0.0

    total_weight = sum(weight for _, weight in weighted)
    if total_weight <= 0.0:
        return 0.0

    score = sum(value * weight for value, weight in weighted) / total_weight
    return max(0.0, min(1.0, score))


def _get_polygon_vertex_count(region: geo.Curve) -> int:
    try:
        success, polyline = region.TryGetPolyline()
        if success and polyline:
            return len(_unique_xy_points(list(polyline)))
    except Exception:
        pass

    try:
        verts = utils.get_vertices(region)
    except Exception:
        return 0

    if not verts:
        return 0

    return len(_unique_xy_points(verts))


def _unique_xy_points(points: List[geo.Point3d], precision: int = 6) -> List[geo.Point3d]:
    unique: List[geo.Point3d] = []
    seen = set()
    for pt in points:
        key = (round(pt.X, precision), round(pt.Y, precision))
        if key in seen:
            continue
        seen.add(key)
        unique.append(pt)
    return unique


def _cross(o: geo.Point3d, a: geo.Point3d, b: geo.Point3d) -> float:
    return (a.X - o.X) * (b.Y - o.Y) - (a.Y - o.Y) * (b.X - o.X)


def _monotone_chain(points: List[geo.Point3d]) -> List[geo.Point3d]:
    """
    Andrew's monotone chain algorithm for 2D convex hull.
    입력은 XY 평면상의 점들.
    """
    pts = sorted(points, key=lambda p: (p.X, p.Y))
    if len(pts) <= 1:
        return pts[:]

    lower: List[geo.Point3d] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: List[geo.Point3d] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    hull = lower[:-1] + upper[:-1]
    return hull
