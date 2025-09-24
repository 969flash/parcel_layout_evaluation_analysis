from __future__ import annotations

import math
from typing import List
import Rhino.Geometry as geo
from units import Block
import utils


def compute(block: Block) -> float:
    """
    블록 형태 점수(placeholder).

    추후, 블록 PSI(정사각형 기준 형태지수)를 분모로 하고
    lot PSI 평균을 분자로 하는 비율을 사용할 수 있습니다.
    현재는 계산 로직 미정 상태로 0.0을 반환합니다.
    """
    block_sq_shape_index = get_sq_shape_index(block.region)
    block_convexity_index = get_convexity_index(block.region)
    lots_sq_shape_index = sum(
        [get_sq_shape_index(lot.region) for lot in block.lots]
    ) / len(block.lots)
    lots_convexity_index = sum(
        [get_convexity_index(lot.region) for lot in block.lots]
    ) / len(block.lots)

    sq_shape_index = lots_sq_shape_index / block_sq_shape_index
    convexity_index = lots_convexity_index / block_convexity_index

    return sq_shape_index


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

    return perim / (4.0 * math.sqrt(area))


def get_convexity_index(region: geo.Curve) -> float:
    """
    볼록성 지수(CI) 계산: A / A_ch

    - A: 원래 영역 면적
    - A_ch: 최소 볼록 다각형(Convex Hull) 면적
    - 결과값은 (0, 1] 범위. 1에 가까울수록 더 볼록함.
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


def _convex_hull_curve(region: geo.Curve) -> geo.Curve | None:
    """
    주어진 닫힌 커브의 평면(월드 XY 가정)에서 2D Convex Hull을 계산해 PolylineCurve로 반환.
    샘플 포인트는 커브 분해 정점 + 균등 분할점 사용.
    """
    # 포인트 수집
    pts: List[geo.Point3d] = []
    try:
        # 세그먼트 정점
        verts = utils.get_vertices(region)
        pts.extend(verts)
        # 균등 분할점 (대략 100분할)
        perim = max(region.GetLength(), 1e-6)
        step = max(perim / 100.0, 1e-3)
        pts.extend(utils.get_pts_by_length(region, step, include_start=True))
    except Exception:
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
