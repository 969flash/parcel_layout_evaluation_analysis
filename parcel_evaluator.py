# r: pyshp, geopandas, networkx

from typing import Dict, List, Any
import importlib
from block_generator import BlockGenerator
from shape_manager import ShapefileManager
import utils, units, shape_manager, block_generator
from units import Block

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

        block_regions = [block.region for block in self.blocks if block.region]
        print(f"Generated {len(block_regions)} block regions.")

        return {
            "num_parcels": len(self.parcels),
            "num_blocks": len(self.blocks),
            "num_block_regions": len(block_regions),
            "blocks": self.blocks,
            "block_regions": block_regions,
        }
