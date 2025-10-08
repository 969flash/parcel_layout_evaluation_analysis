from __future__ import annotations

from typing import Dict, Tuple, List
import importlib
import Rhino.Geometry as geo
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
    buildable_area = 0.0
    for lot in block.lots:
        buildable_area += get_buildable_area(
            lot.region, small_setback_regions, large_setback_regions
        )

    block_area = utils.get_area(block.region)
    print(f"Block area: {block_area}, Buildable area: {buildable_area}")
    return buildable_area / block_area


def get_buildable_area(
    lot_region: geo.Curve,
    small_setback_regions: List[geo.Curve],
    large_setback_regions: List[geo.Curve],
) -> float:
    """
    실질적 건축 가능 영역을 계산합니다.
    """
    # 1. 인접대지경계선, 건축선 적용
    if utils.get_area(lot_region) < constants.LARGE_LOT_AREA:
        buildable_regions = utils.offset_regions_inward(
            [lot_region], constants.SMALL_ADJ_OFFSET
        )
        buildable_regions = utils.get_intersection_regions(
            buildable_regions, small_setback_regions
        )
    else:
        buildable_regions = utils.offset_regions_inward(
            [lot_region], constants.LARGE_ADJ_OFFSET
        )
        buildable_regions = utils.get_intersection_regions(
            buildable_regions, large_setback_regions
        )

    # 2. 건축물 최소 폭 적용
    buildable_regions = utils.simplify_region_with_offset(
        buildable_regions, constants.MIN_BUILDING_WIDTH
    )

    return utils.get_area(buildable_regions)
