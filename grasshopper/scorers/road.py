from __future__ import annotations
from typing import Dict, List, Tuple
import scriptcontext as sc
from units import Block, Lot


# ===============================================================
# ## 설정 (Configuration) ##
# ===============================================================

ROAD_CONDITION_SCORES: Dict[str, float] = {
    "01": 95.83,
    "02": 100.0,
    "03": 98.33,
    "04": 91.67,
    "05": 94.17,
    "06": 87.50,
    "07": 90.00,
    "08": 83.33,
    "09": 85.83,
    "10": 75.00,
    "11": 77.50,
    "12": 0.0,
}

# ===============================================================
# ## 계산 로직 (Scoring Logic) ##
# ===============================================================


def get_score_from_code(road_code: str) -> float:
    """접도 조건 코드를 받아 점수를 반환하는 헬퍼 함수"""
    return ROAD_CONDITION_SCORES.get(road_code, 0.0)


def compute(block: Block) -> float:
    """
    블록의 '구획 접도 효율성 지수'를 계산하여 단일 값으로 반환합니다.
    이 지수는 블록의 잠재력 대비 실제 달성도를 의미합니다.
    """
    if not block.lots:
        return 0.0

    # 블록 내 모든 필지의 점수를 리스트로 저장
    internal_lot_scores = [get_score_from_code(lot.road_adj) for lot in block.lots]

    # 블록의 최대 잠재력 점수를 '내부 필지 중 최고점'으로 추정 (분모)
    inferred_block_max_score = max(internal_lot_scores) if internal_lot_scores else 0.0

    # 블록 내 필지들의 실제 평균 점수 계산 (분자)
    average_internal_score = sum(internal_lot_scores) / len(internal_lot_scores)
    if inferred_block_max_score <= 0:
        raise Exception(
            "Inferred block max score is zero or negative, cannot compute efficiency index."
        )
    # 구획 접도 효율성 지수 계산
    access_efficiency_index = average_internal_score / inferred_block_max_score

    return access_efficiency_index
