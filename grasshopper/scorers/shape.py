from __future__ import annotations

import math
from typing import List
import Rhino.Geometry as geo
import ghpythonlib.components as ghcomp  # type: ignore
from units import Block
import utils
import os

from constants import (
    SHAPE_BLOCK_INFLUENCE,
    SHAPE_CONVEXITY_WEIGHT,
    SHAPE_CIRCULARITY_WEIGHT,
    SHAPE_SQUARENESS_WEIGHT,
)


def compute(block: Block) -> float:
    """Return the shape score for a block.

    1) 각 필지의 RSI 평균을 계산하고
    2) 블록 외곽선의 RSI를 기반으로 'ugly multiplier'를 만들어
    3) 두 값을 곱해 최종 점수를 산출합니다.
    """
    if not block.lots:
        return 0.0

    lot_scores = [get_rsi(lot.region) for lot in block.lots]
    if not lot_scores:
        return 0.0

    lot_avg_rsi = sum(lot_scores) / len(lot_scores)

    block_rsi = get_rsi(block.region)
    block_multiplier = _compute_block_multiplier(block_rsi)

    final_score = lot_avg_rsi * block_multiplier

    return final_score


def get_rsi(region: geo.Curve | None) -> float:
    """Return the RSI value (0~1) for a single region."""
    convexity = get_convexity_index(region)
    circularity = get_circularity_index(region)
    squareness = get_squareness_index(region)

    rsi = (
        (convexity * SHAPE_CONVEXITY_WEIGHT)
        + (circularity * SHAPE_CIRCULARITY_WEIGHT)
        + (squareness * SHAPE_SQUARENESS_WEIGHT)
    )

    return rsi


def get_convexity_index(region: geo.Curve) -> float:
    """
    볼록성 지수(CI) 계산: A / A_ch

    - A: 원래 영역 면적
    - A_ch: 최소 볼록 다각형(Convex Hull) 면적
    - 결과값은 (0, 1] 범위. 1에 가까울수록 더 볼록함.
    - 자루형, ㄷ자형, 별 모양 등 움푹 파인 필지에 페널티 부여
    """
    if region is None:
        raise ValueError("Region curve is required to compute convexity.")
    if not getattr(region, "IsClosed", False):
        raise ValueError("Region curve must be closed to compute convexity.")

    try:
        area = float(utils.get_area(region))
    except Exception:
        return 0.0
    if area <= 0.0:
        return 0.0

    vertices = utils.get_vertices(region)
    hull_crv = ghcomp.ConvexHull(vertices).hull

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
    if region is None:
        raise ValueError("Region curve is required to compute circularity.")
    if not getattr(region, "IsClosed", False):
        raise ValueError("Region curve must be closed to compute circularity.")

    try:
        area = utils.get_area(region)
        perim = utils.get_length(region)
    except Exception:
        return 0.0

    # Isoperimetric Quotient 공식
    circularity = (4.0 * math.pi * area) / (perim * perim)

    # 이론적으로 1.0을 초과할 수 없지만, 부동소수점 오차로 인해 약간 초과할 수 있음
    return circularity


def get_squareness_index(region: geo.Curve) -> float:
    """정사각형 기반 정방향성 지표를 반환."""
    bbox = utils.get_min_bbox(region)

    width = max(bbox.X.Length, 0.0)
    height = max(bbox.Y.Length, 0.0)

    if width <= 0.0 or height <= 0.0:
        return 0.0

    aspect_ratio = min(width, height) / max(width, height)

    vertex_count = len(utils.get_vertices(region))
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

    return aspect_ratio * vertex_penalty


def _compute_block_multiplier(block_rsi: float) -> float:
    """Return the block-level adjustment multiplier."""
    if block_rsi <= 0.0:
        return 1.0 - SHAPE_BLOCK_INFLUENCE
    return (block_rsi * SHAPE_BLOCK_INFLUENCE) + (1.0 - SHAPE_BLOCK_INFLUENCE)
