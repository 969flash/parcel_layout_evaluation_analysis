from typing import Dict, List, Any
from units import Block, LayoutScore
import scorers  # type: ignore


def evaluate(blocks: List[Block]) -> List[Block]:
    print(f"Loaded {len(blocks)} blocks.")

    for block in blocks:
        block.layout_score = LayoutScore(
            region_score=scorers.compute_region(block),
            shape_score=scorers.compute_shape(block),
            road_score=scorers.compute_road(block),
            topo_score=scorers.compute_topo(block),
        )

    return blocks
