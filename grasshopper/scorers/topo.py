from __future__ import annotations

from typing import Dict, Tuple
from units import Block


def compute(block: Block) -> float:
    """
    Compute topology-based score for a block.
    블록의 고도 기반 구획 품질을 평가합니다.

    Args:
        block: 평가할 Block 객체

    Returns:
        float: 0~1 사이의 구획 품질 점수
               - 1.0: 완벽한 평탄화
               - 0.5: 보통 수준의 구획 (필지 1개 특례)
               - 0.0: 개선 없음 또는 계산 불가

    평가 기준:
        점수 = 1 - (필지 평균 고저차 / 블록 전체 고저차)
    """

    # 1) 블록의 max/min 높이 확인 (없으면 계산 불가)
    block_max = getattr(block, "max_height", None)
    block_min = getattr(block, "min_height", None)
    if block_max is None or block_min is None:
        return 0.0

    # 2) 유효한 높이 데이터가 있는 필지들 필터링 (lot.max/min 둘 다 있어야 함)
    lots = getattr(block, "lots", []) or []
    valid_lots = [
        lot
        for lot in lots
        if getattr(lot, "max_height", None) is not None
        and getattr(lot, "min_height", None) is not None
    ]

    # 3) 엣지 케이스 처리
    if not valid_lots:
        return 0.0
    if len(valid_lots) == 1:
        return 0.5

    # 4) 블록 고저차 계산 (절대값으로 안전 처리)
    block_relief = abs(float(block_max) - float(block_min))
    # 실질적 평지로 간주되는 작은 기복 (예: 0.5m 미만)
    if block_relief < 0.5:
        return 1.0

    # 5) 각 필지의 고저차 계산 및 평균 산출
    lot_reliefs = [
        abs(float(lot.max_height) - float(lot.min_height)) for lot in valid_lots
    ]
    if not lot_reliefs:
        return 0.0
    avg_lot_relief = sum(lot_reliefs) / float(len(lot_reliefs))

    # 6) 구획 품질 점수 계산
    # 필지 평균 고저차가 블록 고저차보다 크면 0.0 (개선 없음)
    if avg_lot_relief > block_relief:
        return 0.0
    score = 1.0 - (avg_lot_relief / block_relief)

    # 7) 0~1 범위로 클램핑 후 반환
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return float(score)
