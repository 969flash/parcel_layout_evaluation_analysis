# r: pyshp, geopandas, networkx

from typing import Dict, List, Any
import importlib
from block_generator import BlockGenerator
from shape_manager import ShapefileManager
import utils, units, shape_manager, block_generator
from units import Block
import scriptcontext as sc

# 모듈 새로고침
importlib.reload(utils)
importlib.reload(units)


class LayoutScore:
    def __init__(
        self,
        region_score: float,
        shape_score: float = 0.0,
        road_score: float = 0.0,
        topo_score: float = 0.0,
        details: Dict[str, Any] = None,
    ):
        self.region_score = region_score
        self.shape_score = shape_score
        self.road_score = road_score
        self.topo_score = topo_score
        self.details = details or {}

    def __repr__(self):
        return f"LayoutScore(region_score={self.region_score}, shape_score={self.shape_score}, road_score={self.road_score}, topo_score={self.topo_score}, details={self.details})"


class ParcelEvaluator:
    def evaluate(self, blocks: List[Block]) -> Dict[str, Any]:
        print(f"Loaded {len(blocks)} blocks.")

        layout_scores = []
        for block in blocks:
            region_score = self._get_regions_score(block)
            shape_score = self._get_shape_score(block)
            road_score = self._get_road_score(block)
            topo_score = self._get_topo_score(block)
            layout_scores.append(
                LayoutScore(region_score, shape_score, road_score, topo_score)
            )

        return layout_scores

    def _get_regions_score(self, block: Block) -> float:

        result = utils.offset_regions_inward(block.region, 0.5)
        if len(result) != 1:
            raise ValueError("오프셋 이후 블록 경계가 단일 커브가 아닙니다.")
        block_region = result[0]

        lots_regions = []
        for lot in block.lots:
            lot_regions = utils.offset_regions_inward(lot.region, 0.5)
            lots_regions.extend(lot_regions)

        return sum(utils.get_area(region) for region in lots_regions) / utils.get_area(
            block_region
        )

    def _get_shape_score(self, block: Block) -> float:
        # Placeholder for shape score calculation
        return 0.0

    def _get_road_score(self, block: Block) -> float:
        # Placeholder for road score calculation
        return 0.0

    def _get_topo_score(self, block: Block) -> float:
        # Placeholder for topology score calculation
        return 0.0
