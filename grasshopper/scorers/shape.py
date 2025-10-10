from __future__ import annotations

import math
from typing import List
import Rhino.Geometry as geo
from units import Block
import utils


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

    # 가중치 설정 (균형 있게 시작)
    w1 = 0.5  # 볼록성 가중치
    w2 = 0.5  # 원형성 가중치

    # 각 필지의 RSI 점수 계산
    lot_rsi_scores = []
    for lot in block.lots:
        # Component 1: 볼록성 점수
        score_convexity = get_convexity_index(lot.region)

        # Component 2: 원형성 점수
        score_circularity = get_circularity_index(lot.region)

        # RSI 계산
        rsi = w1 * score_convexity + w2 * score_circularity
        lot_rsi_scores.append(rsi)

    # 블록 내 필지들의 평균 RSI 점수 반환
    return sum(lot_rsi_scores) / len(lot_rsi_scores)


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
