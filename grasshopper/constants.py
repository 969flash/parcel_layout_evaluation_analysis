# Tolerances
TOL = 0.0001  # 기본 허용 오차
DIST_TOL = 0.01
AREA_TOL = 0.1
RAW_TOL = 0.5
OP_TOL = 0.00001
CLIPPER_TOL = 0.0000000001

# Constants
BIGNUM = 10000000
ROUNDING_PRECISION = 6  # 반올림 소수점 자리수

# Setbacks and Offsets (in meters)
SMALL_SETBACK = 1.0
LARGE_SETBACK = 2.0
SMALL_ADJ_OFFSET = 0.5
LARGE_ADJ_OFFSET = 1.5

# Building Constraints (in meters)
MIN_BUILDING_WIDTH = 4.0

# Area Thresholds (in square meters)
LARGE_LOT_AREA = 660.0

# Shape Scoring Weights
SHAPE_COMPONENT_WEIGHTS = {
	"convexity": 0.3,
	"circularity": 0.3,
	"squareness": 0.4,
}

# Proportion of the block-level RSI used as a multiplier for lot averages
SHAPE_BLOCK_INFLUENCE = 0.2
