from __future__ import annotations

# -*- coding: utf-8 -*-
# r: pyshp
import importlib
from typing import List, Tuple, Any, Optional, TYPE_CHECKING
import shapefile
import importlib

# Rhino-specific imports
import Rhino
import Rhino.Geometry as geo
import ghpythonlib.components as ghcomp

# Local class imports
# 클래스는 units.py에 정의되어 있다고 가정합니다.
from units import Parcel, Road, Lot, Block
from constants import TOL
import utils, units
from pathlib import Path
from datetime import datetime

importlib.reload(utils)
importlib.reload(units)

if TYPE_CHECKING:
    from units import Block


class ShapefileManager:
    """
    - 기능 1: SHP 파일로부터 Parcel 객체 생성
    - 기능 2: Block 객체 리스트를 받아 SHP 파일로 저장

    생성자에서는 파일 경로를 받지 않습니다. 각 기능 메서드에서 경로를 인자로 받습니다.
    """

    def __init__(self) -> None:
        self._encoding: Optional[str] = (
            None  # 마지막 읽기에 사용한 DBF 인코딩 (또는 .cpg에서 추출)
        )
        self._prj_wkt: Optional[str] = None  # 마지막 읽기 소스의 .prj WKT 텍스트

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

    def get_parcels_from_shapes(self, file_path: str) -> List[Parcel]:
        """
        모든 Shape로부터 Parcel 객체 리스트를 생성합니다.
        파일 경로는 이 메서드 호출 시 인자로 전달합니다.
        """
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
                # 인코딩 기록: 명시적 인코딩을 사용했다면 저장
                if enc:
                    self._encoding = enc
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
            shapes = sf.shapes()
        except Exception as e:
            raise RuntimeError(f"Failed to read shapes(): {e}")
        try:
            records = sf.records()
        except Exception as e:
            raise RuntimeError(f"Failed to read records(): {e}")
        try:
            raw_fields = sf.fields[1:]  # 첫 필드는 DeletionFlag
            fields = [f[0] for f in raw_fields]
        except Exception as e:
            raise RuntimeError(f"Failed to parse fields: {e}")

        if not fields:
            print("[WARN] No fields parsed; DBF may be missing or corrupt")

        # 좌표계/인코딩 부가 정보 보존: .prj/.cpg
        try:
            prj_path = Path(file_path).with_suffix(".prj")
            if prj_path.exists():
                # WKT는 일반 텍스트. 인코딩은 보통 ASCII/UTF-8로 문제 없음
                self._prj_wkt = prj_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
        try:
            # .cpg 파일이 있다면 인코딩으로 활용 (명시적 인코딩 미사용 시)
            if not self._encoding:
                cpg_path = Path(file_path).with_suffix(".cpg")
                if cpg_path.exists():
                    enc = cpg_path.read_text(encoding="utf-8", errors="ignore").strip()
                    if enc:
                        self._encoding = enc
        except Exception:
            pass

        parcels: List[Parcel] = []
        for shape, record in zip(shapes, records):
            parcel = self._create_parcel_from_shape(shape, record, fields)
            if parcel:
                parcels.append(parcel)
        return parcels

    # ==============================================================
    # 저장 기능: Block 리스트를 SHP로 저장
    # ==============================================================
    def save_blocks_to_shapefile(self, blocks: List[Block], dir_path: str) -> str:
        """
        Block.region(폴리곤)을 geometry로 저장하고, Block.layout_score의 4개 점수를 속성으로 기록합니다.

        - 필드: BLOCK_ID, REGION, SHAPE, ROAD, TOPO
        - geometry: Polygon (단일 외곽 링; 현재 Block.region만 저장)
        """
        if not blocks:
            # 빈 입력이면 저장하지 않고 빈 경로 반환
            return ""

        # 출력 디렉토리 준비
        out_dir = Path(dir_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        # 날짜 기반 파일명 + 증분: YYYYMMDD_{n}_blocks.shp
        date_str = datetime.now().strftime("%Y%m%d")
        n = 1
        while True:
            base_name = f"{date_str}_{n}_blocks"
            shp_path = out_dir / f"{base_name}.shp"
            if not shp_path.exists():
                break
            n += 1

        # shapefile Writer 설정
        # 읽기에서 기억한 인코딩을 사용 (기본: utf-8)
        writer_encoding = self._encoding or "utf-8"
        w = shapefile.Writer(
            str(shp_path), shapeType=shapefile.POLYGON, encoding=writer_encoding
        )
        w.autoBalance = 1

        # 필드 정의 (DBF 제약: 이름 <= 10자)
        w.field("BLOCK_ID", "N")
        w.field("REGION", "F", 10, 5)
        w.field("SHAPE", "F", 10, 5)
        w.field("ROAD", "F", 10, 5)
        w.field("TOPO", "F", 10, 5)

        for block in blocks:
            # 점 리스트 생성 (폴리라인 근사)
            pts = utils.get_vertices(block.region)
            pts = [(pt.X, pt.Y) for pt in pts] + [(pts[0].X, pts[0].Y)]  # 닫기

            if len(pts) < 4:
                # 최소 3점 + 폐합 필요
                continue

            # 속성값: layout_score 존재 시 사용, 없으면 0.0 기본값
            region_s = block.layout_score.region_score
            shape_s = block.layout_score.shape_score
            road_s = block.layout_score.road_score
            topo_s = block.layout_score.topo_score

            # geometry + record 추가
            w.poly([pts])  # 단일 외곽 링
            w.record(
                int(getattr(block, "id", -1)),
                float(region_s),
                float(shape_s),
                float(road_s),
                float(topo_s),
            )

        # 파일 저장
        w.close()

        # .prj/.cpg 파일 동반 저장 (읽은 설정 재사용)
        try:
            if self._prj_wkt:
                (shp_path.with_suffix(".prj")).write_text(
                    self._prj_wkt, encoding="utf-8"
                )
        except Exception:
            pass
        try:
            if writer_encoding:
                (shp_path.with_suffix(".cpg")).write_text(
                    writer_encoding, encoding="utf-8"
                )
        except Exception:
            pass

        return str(shp_path)
