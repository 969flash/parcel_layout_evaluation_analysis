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


if __name__ == "__main__":
    # 실행 위치 확인 (1번)

    abs_shp = globals().get("shapefile_path", None)
    save_path = globals().get("save_path", None)
    shapefile_manager = ShapefileManager()
    parcels = shapefile_manager.get_parcels_from_shapes(str(abs_shp))

    block_generator = BlockGenerator()
    print(f"Loaded {len(parcels)} parcels.")
    blocks = block_generator.generate(parcels)

    print("Block generation complete.")
    print(f"Generated {len(blocks)} blocks.")

    block_regions = [block.region for block in blocks if block.region]

    print(f"Generated {len(block_regions)} block regions.")

    blocks = parcel_evaluator.evaluate(blocks)

    shapefile_manager.save_blocks_to_shapefile(blocks, save_path)
    print("Layout evaluation complete.")
