# -*- coding: utf-8 -*-
# r: pyshp
import importlib
from typing import List, Tuple, Any, Optional, Union
import shapefile
import importlib

# Rhino-specific imports
import Rhino
import Rhino.Geometry as geo
import ghpythonlib.components as ghcomp

# Local class imports
# 클래스는 units.py에 정의되어 있다고 가정합니다.
from units import Parcel, Road, Lot
from constants import TOL
import utils, units

importlib.reload(utils)
importlib.reload(units)


class ShapefileManager:
    """
    Shapefile 로딩, Parcel 생성 및 분석 과정을 캡슐화한 관리자 클래스.
    파일 경로만으로 관련 작업을 쉽게 수행할 수 있도록 API를 제공합니다.
    """

    def __init__(self, file_path: str):
        # 상세 디버그: 인코딩 순차 시도 + 내부 상태 점검
        enc_attempts = ["utf-8", "cp949", None]
        last_errors = []
        sf = None
        for enc in enc_attempts:
            try:
                if enc:
                    sf = shapefile.Reader(file_path, encoding=enc)
                else:
                    sf = shapefile.Reader(file_path)
                print(f"[ShapefileManager] opened OK with encoding={enc}")
                break
            except Exception as e:
                last_errors.append((enc, repr(e)))
        if sf is None:
            detail = "\n".join([f"  - {enc}: {err}" for enc, err in last_errors])
            raise RuntimeError(f"Failed to open shapefile: {file_path}\n{detail}")

        # 원시 내부 속성(필요시) 확인
        try:
            print("[DEBUG] file_path:", file_path)
            print(
                "[DEBUG] numShapes:",
                sf.numShapes() if hasattr(sf, "numShapes") else "n/a",
            )
            print("[DEBUG] fields raw:", sf.fields if hasattr(sf, "fields") else "n/a")
        except Exception as e:
            print("[DEBUG] meta access error:", e)

        try:
            self._shapes = sf.shapes()
        except Exception as e:
            raise RuntimeError(f"Failed to read shapes(): {e}")
        try:
            self._records = sf.records()
        except Exception as e:
            raise RuntimeError(f"Failed to read records(): {e}")
        try:
            raw_fields = sf.fields[1:]  # 첫 필드는 DeletionFlag
            self._fields = [f[0] for f in raw_fields]
        except Exception as e:
            raise RuntimeError(f"Failed to parse fields: {e}")

        if not self._fields:
            print("[WARN] No fields parsed; DBF may be missing or corrupt")

    def _get_field_value(
        self,
        record: List[Any],
        fields: List[str],
        field_name: str,
        default: Any = "Unknown",
    ) -> Any:
        """레코드에서 특정 필드 이름을 이용해 값을 안전하게 추출합니다."""
        try:
            index = fields.index(field_name)
            return record[index]
        except (ValueError, IndexError):
            return default

    def _get_part_indices(self, shape: Any) -> List[Tuple[int, int]]:
        """Shape의 각 파트(part)의 시작과 끝 인덱스 리스트를 반환합니다."""
        if not hasattr(shape, "parts") or len(shape.parts) <= 1:
            return [(0, len(shape.points))]

        parts = list(shape.parts) + [len(shape.points)]
        return [(parts[i], parts[i + 1]) for i in range(len(parts) - 1)]

    def _get_curve_from_points(
        self, points: List[Tuple[float, float]], start_idx: int, end_idx: int
    ) -> Optional[geo.PolylineCurve]:
        """점 리스트의 특정 구간으로 PolylineCurve를 생성합니다."""
        if end_idx - start_idx < 3:
            return None

        # 닫힌 커브인지 확인
        first_pt, last_pt = points[start_idx], points[end_idx - 1]
        if first_pt[0] != last_pt[0] or first_pt[1] != last_pt[1]:
            return None

        curve_points = [geo.Point3d(p[0], p[1], 0) for p in points[start_idx:end_idx]]
        curve = geo.PolylineCurve(curve_points)
        return curve if curve and curve.IsValid else None

    def _get_curves_from_shape(
        self,
        shape: Any,
    ) -> Tuple[Optional[geo.PolylineCurve], List[geo.PolylineCurve]]:
        """
        단일 Shape에서 외부 경계(boundary)와 내부 홀(hole) 커브들을 추출합니다.
        """
        part_indices = self._get_part_indices(shape)

        boundary_region = None
        hole_regions = []

        for i, (start_idx, end_idx) in enumerate(part_indices):
            curve = self._get_curve_from_points(shape.points, start_idx, end_idx)
            if curve:
                if i == 0:  # 첫 번째 파트는 외부 경계로 가정
                    boundary_region = curve
                else:
                    hole_regions.append(curve)

        # 파트가 하나이고 닫혀있지 않은 폴리곤 예외 처리
        if boundary_region is None and len(part_indices) == 1:
            points = [geo.Point3d(pt[0], pt[1], 0) for pt in shape.points]
            if len(points) >= 3:
                if points[0].DistanceTo(points[-1]) > TOL:
                    points.append(points[0])  # 강제로 닫기
                curve = geo.PolylineCurve(points)
                if curve and curve.IsValid:
                    boundary_region = curve

        return boundary_region, hole_regions

    def _create_parcel_from_shape(
        self, shape: Any, record: List[Any], fields: List[str]
    ) -> Optional[Parcel]:
        """Shape와 record 데이터로 단일 Parcel(Lot 또는 Road) 객체를 생성합니다."""
        boundary_region, hole_regions = self._get_curves_from_shape(shape)

        if not boundary_region or not boundary_region.IsValid:
            return None

        pnu = self._get_field_value(record, fields, "A1")
        jimok = self._get_field_value(record, fields, "A11")

        if jimok == "도로" or not jimok:
            parcel = Road(boundary_region, pnu, jimok, record, hole_regions)
        else:
            parcel = Lot(boundary_region, pnu, jimok, record, hole_regions)

        # 지오메트리 전처리 후 유효한 경우에만 반환
        return parcel  # if parcel.preprocess_curve() else None

    def get_parcels_from_shapes(self) -> List[Parcel]:
        """모든 Shape로부터 Parcel 객체 리스트를 생성합니다."""
        parcels = []
        for shape, record in zip(self._shapes, self._records):
            parcel = self._create_parcel_from_shape(shape, record, self._fields)
            if parcel:
                parcels.append(parcel)
        return parcels
