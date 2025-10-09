from __future__ import annotations

from typing import Dict, Tuple, List
import importlib
import Rhino.Geometry as geo
import scriptcontext as sc
import utils, units, constants
from units import Block

importlib.reload(utils)
importlib.reload(units)
importlib.reload(constants)


def compute(block: Block) -> float:
    """
    Compute region-based score for a block.
    Return (score).
    """
    # 건축선
    small_setback_regions = utils.offset_regions_inward(
        block.region, constants.SMALL_SETBACK
    )
    large_setback_regions = utils.offset_regions_inward(
        block.region, constants.LARGE_SETBACK
    )

    # 인접대지 경계선, 건축선 적용된 건축 가능 영역

    # 개별 대지의 건축 가능 영역 계산
    buildable_lot_area = 0.0
    for lot in block.lots:
        buildable_lot_area += get_buildable_area(
            lot.region, small_setback_regions, large_setback_regions
        )

    # 전체 블록의 건축 가능 영역 계산
    buildable_block_area = get_buildable_area(
        block.region, small_setback_regions, large_setback_regions
    )

    score = buildable_lot_area / buildable_block_area

    return score


def get_buildable_area(
    region: geo.Curve,
    small_setback_regions: List[geo.Curve],
    large_setback_regions: List[geo.Curve],
) -> float:
    """
    실질적 건축 가능 영역을 계산합니다.
    """
    # 1. 인접대지경계선, 건축선 적용
    if utils.get_area(region) < constants.LARGE_LOT_AREA:
        buildable_regions = utils.offset_regions_inward(
            [region], constants.SMALL_ADJ_OFFSET
        )
        buildable_regions = utils.get_intersection_regions(
            buildable_regions, small_setback_regions
        )
    else:
        buildable_regions = utils.offset_regions_inward(
            [region], constants.LARGE_ADJ_OFFSET
        )
        buildable_regions = utils.get_intersection_regions(
            buildable_regions, large_setback_regions
        )

    # 2. 건축물 최소 폭 적용
    # miter 옵션을 2로 설정하여 모서리 부분이 너무 깎이지 않도록 함(60도 미만 스파이크 생성 방지)
    buildable_regions = utils.simplify_regions_with_offset(
        buildable_regions, constants.MIN_BUILDING_WIDTH, miter=2
    )

    return utils.get_area(buildable_regions)
