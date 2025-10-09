from typing import Dict, List, Any
from units import Block, LayoutScore
import importlib
import scorers  # type: ignore


def _hot_reload_scorers() -> bool:
    """Reload scorer submodules and then the scorers package to refresh re-exported bindings.

    This avoids stale references from `scorers/__init__.py` aliasing (e.g., compute_region)
    when editing `scorers.region` etc. during GH dev loops.
    """
    try:
        # Ensure submodules are importable; if not yet imported, import them first.
        from scorers import region as _region, shape as _shape, road as _road, topo as _topo  # type: ignore

        importlib.reload(_region)
        importlib.reload(_shape)
        importlib.reload(_road)
        importlib.reload(_topo)
        # Rebind `compute_*` aliases in scorers/__init__.py to the freshly reloaded submodules
        importlib.reload(scorers)
        return True
    except Exception as e:
        # Non-fatal: keep going with whatever is loaded
        print(f"[EVALUATION] hot-reload skipped: {e}")
        return False


import importlib

importlib.reload(scorers)


def evaluate(blocks: List[Block]) -> List[Block]:
    # During interactive GH development, keep scorers fresh
    _hot_reload_scorers()

    print(f"[EVALUATION] Loaded {len(blocks)} blocks.")

    for block in blocks:
        block.layout_score = LayoutScore(
            region_score=scorers.compute_region(block),
            shape_score=scorers.compute_shape(block),
            road_score=scorers.compute_road(block),
            topo_score=scorers.compute_topo(block),
        )

    return blocks
