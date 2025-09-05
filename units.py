import Rhino.Geometry as geo
from typing import List, Any, Optional, Tuple
from constants import TOL
import importlib
import scriptcontext as sc
import utils
import constants
from constants import RAW_TOL

importlib.reload(utils)
importlib.reload(constants)


class Parcel:
    """기본 필지 클래스 (지오메트리 보관용)

    전처리 로직은 utils의 함수에 위임하여 중복을 줄입니다.
    """

    def __init__(
        self,
        curve_crv: geo.Curve,
        pnu: str,
        jimok: str,
        record: List[Any],
        hole_regions: Optional[List[geo.Curve]] = None,
    ):
        self.region: geo.Curve = curve_crv  # 외부 경계 커브
        self.hole_regions: List[geo.Curve] = hole_regions or []  # 내부 구멍들
        self.pnu = pnu
        self.jimok = jimok
        self.record = record

    def preprocess_curve(self) -> bool:
        """커브 전처리 (invalid 제거, 자체교차 제거, 단순화)

        구현은 utils.preprocess_curve_util에 위임하여 순환 의존성을 피하기 위해 지연 임포트를 사용합니다.
        """
        if not self.region or not getattr(self.region, "IsValid", False):
            return False

        # 지연 임포트로 순환 의존성 방지
        try:
            import utils  # type: ignore
        except Exception:
            return False

        result = self._preprocess_curve_util(self.region, self.hole_regions)
        if result is None:
            return False

        region, holes = result
        self.region = region
        self.hole_regions = holes
        return True

    def _preprocess_curve_util(
        self, region: geo.Curve, hole_regions: Optional[List[geo.Curve]]
    ) -> Optional[Tuple[geo.Curve, List[geo.Curve]]]:
        """
        커브의 자체 교차를 제거하고 단순화하여 유효한 폴리곤으로 전처리합니다.
        홀(hole) 커브들도 함께 처리합니다.
        """

        if region is None or not getattr(region, "IsValid", False):
            return None

        # 자체교차 확인 및 단순화
        try:
            if geo.Intersect.Intersection.CurveSelf(region, TOL):
                simplified = region.Simplify(geo.CurveSimplifyOptions.All, 0.1, 1.0)
                region = simplified or region
        except Exception:
            pass  # 실패 시 원본 사용

        # 일반 단순화
        try:
            simplified = region.Simplify(geo.CurveSimplifyOptions.All, 0.1, 1.0)
            region = simplified or region
        except Exception:
            pass

        # 홀 커브들 단순화
        valid_holes: List[geo.Curve] = []
        for hole in hole_regions or []:
            try:
                if hole and hole.IsValid:
                    simplified_hole = hole.Simplify(
                        geo.CurveSimplifyOptions.All, 0.1, 1.0
                    )
                    valid_holes.append(simplified_hole or hole)
            except Exception:
                continue

        return region, valid_holes


class Road(Parcel):
    """도로 클래스"""

    pass


class Lot(Parcel):
    """대지 클래스"""

    def __init__(
        self,
        curve_crv: geo.Curve,
        pnu: str,
        jimok: str,
        record: List[Any],
        hole_regions: Optional[List[geo.Curve]] = None,
    ):
        super().__init__(curve_crv, pnu, jimok, record, hole_regions)
        self.is_flag_lot: bool = False  # 자루형 토지 여부
        self.has_road_access: bool = False  # 도로 접근 여부


class Block:
    def __init__(self, lots: List[Lot]):
        self.lots = lots
        self.region: geo.Curve = None  # 블록 경계
        # 막힌 도로를 포함한 블록 여부
        self.is_donut = False
        self._set_block_region()

    def _set_block_region(self) -> None:
        """주어진 Lot들의 경계를 생성합니다."""
        # 모든 Lot의 경계를 합쳐서 하나의 경계로 만듭니다.
        lot_regions = [lot.region for lot in self.lots if lot.region]
        offset_regions = utils.offset_regions_outward(lot_regions, RAW_TOL)
        block_regions = utils.get_union_regions(offset_regions)
        if len(block_regions) != 1:
            block_region = self._get_out_region(block_regions)
            self.is_donut = True

        else:
            block_region = block_regions[0]

        block_region = utils.offset_regions_inward(block_region, RAW_TOL)

        if len(block_region) != 1:
            raise ValueError("오프셋 이후 블록 경계가 단일 커브가 아닙니다.")
        self.region = block_region[0]

    def _get_out_region(self, regions: List[geo.Curve]) -> geo.Curve:
        """가장 바깥쪽의 영역 커브를 반환합니다."""
        if len(regions) == 1:
            return regions[0]

        out_region = None

        for candidate in regions:
            contains_all = True
            for other in regions:
                if other is candidate:
                    continue
                if not utils.is_region_inside(other, candidate):
                    contains_all = False
                    break
            if contains_all:
                out_region = candidate
                break

        if out_region is None:
            raise ValueError("모든 영역을 포함하는 단일 외곽 영역을 찾을 수 없습니다.")

        return out_region
