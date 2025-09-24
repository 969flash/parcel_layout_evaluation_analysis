from typing import Dict, List, Any
from units import Block
import scorers  # type: ignore


class LayoutScore:
    def __init__(
        self,
        block_id=None,
        region_score: float = 0.0,
        shape_score: float = 0.0,
        road_score: float = 0.0,
        topo_score: float = 0.0,
    ):
        self.block_id = block_id
        self.region_score = region_score
        self.shape_score = shape_score
        self.road_score = road_score
        self.topo_score = topo_score

    def __repr__(self):
        # 출력용 문자열 반환
        return f"LayoutScore(region_score={self.region_score}, shape_score={self.shape_score}, road_score={self.road_score}, topo_score={self.topo_score})"


class ParcelEvaluator:
    def evaluate(self, blocks: List[Block]) -> List["LayoutScore"]:
        print(f"Loaded {len(blocks)} blocks.")

        layout_scores: List[LayoutScore] = []
        for block in blocks:

            layout_scores.append(
                LayoutScore(
                    block_id=block.id,
                    region_score=scorers.compute_region(block),
                    shape_score=scorers.compute_shape(block),
                    road_score=scorers.compute_road(block),
                    topo_score=scorers.compute_topo(block),
                )
            )

        return layout_scores
