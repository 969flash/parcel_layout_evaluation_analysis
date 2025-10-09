from typing import Dict, List, Any
from units import Block, LayoutScore
import importlib
import scorers  # type: ignore

importlib.reload(scorers)


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


def evaluate(blocks: List[Block]) -> List[Block]:
    # During interactive GH development, keep scorers fresh
    _hot_reload_scorers()

    total = len(blocks)
    print(f"[EVALUATION] Loaded {total} blocks.")

    # Error counters per scorer and totals
    err_region = err_shape = err_road = err_topo = 0
    err_total = 0
    skipped_blocks = 0

    evaluated_blocks: List[Block] = []

    for block in blocks:
        try:

            # 단일 필지 블록인 경우, 접도 효율성 지수를 1.0으로 설정
            if len(block.lots) == 1:
                block.layout_score = LayoutScore(
                    region_score=1.0,
                    shape_score=1.0,
                    road_score=1.0,
                    topo_score=1.0,
                )
                evaluated_blocks.append(block)
                continue

            # Compute each score with isolated error handling so we know which failed
            try:
                r_region = scorers.compute_region(block)
            except Exception:
                err_region += 1
                raise

            try:
                r_shape = scorers.compute_shape(block)
            except Exception:
                err_shape += 1
                raise

            try:
                r_road = scorers.compute_road(block)
            except Exception:
                err_road += 1
                raise

            try:
                r_topo = scorers.compute_topo(block)
            except Exception:
                err_topo += 1
                raise

            # Only assign if all succeeded
            block.layout_score = LayoutScore(
                region_score=r_region,
                shape_score=r_shape,
                road_score=r_road,
                topo_score=r_topo,
            )
            evaluated_blocks.append(block)

        except Exception:
            # Count one error occurrence for this block (already attributed above)
            err_total += 1
            skipped_blocks += 1
            # Skip this block entirely
            continue

    print(
        "[EVALUATION] Done. success={}/{} skipped={} errors total={} (region={} shape={} road={} topo={})".format(
            len(evaluated_blocks),
            total,
            skipped_blocks,
            err_total,
            err_region,
            err_shape,
            err_road,
            err_topo,
        )
    )

    return evaluated_blocks
