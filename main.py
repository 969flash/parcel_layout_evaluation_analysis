# r: pyshp, geopandas, networkx

from typing import Dict, List, Any
import importlib
from block_generator import BlockGenerator
from shape_manager import ShapefileManager
import utils, units, shape_manager, block_generator, parcel_evaluator

# 모듈 새로고침
importlib.reload(utils)
importlib.reload(units)
importlib.reload(shape_manager)
importlib.reload(block_generator)
importlib.reload(parcel_evaluator)

REL_FILE_PATH = "DATA/AL_D194_11680_20250123.shp"


if __name__ == "__main__":
    # 실행 위치 확인 (1번)
    from pathlib import Path as _P

    print("[CWD]", _P.cwd())
    print("[MAIN __file__]", __file__)
    abs_shp = (_P(__file__).parent / REL_FILE_PATH).resolve()
    print("[Resolved SHP]", abs_shp)
    if not abs_shp.exists():
        raise FileNotFoundError(f"Shapefile not found: {abs_shp}")
    else:
        print(f"SHP file found: {abs_shp}")

    shapefile_manager = ShapefileManager(str(abs_shp))
    parcels = shapefile_manager.get_parcels_from_shapes()

    block_generator = BlockGenerator()
    print(f"Loaded {len(parcels)} parcels.")
    blocks = block_generator.generate(parcels)

    print("Block generation complete.")
    print(f"Generated {len(blocks)} blocks.")

    block_regions = [block.region for block in blocks if block.region]

    print(f"Generated {len(block_regions)} block regions.")

    parcel_evaluator = parcel_evaluator.ParcelEvaluator()
    layout_scores = parcel_evaluator.evaluate(blocks)
    print("Layout evaluation complete.")
