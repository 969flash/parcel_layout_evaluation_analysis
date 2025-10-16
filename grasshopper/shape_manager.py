from __future__ import annotations

# -*- coding: utf-8 -*-
# r: pyshp
import importlib
import os
from typing import List, Tuple, Any, Optional, TYPE_CHECKING, Dict
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
from pathlib import Path, PureWindowsPath
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
        # 마지막 읽기에 사용한 DBF 인코딩(또는 .cpg에서 추출)
        self._encoding = None  # type: Optional[str]
        # 마지막 읽기 소스의 .prj WKT 텍스트
        self._prj_wkt = None  # type: Optional[str]
        # Grasshopper 실행 시 작업 디렉토리가 일정하지 않으므로, 모듈 기준 루트를 캐시해둔다.
        self._module_root = Path(__file__).resolve().parent
        self._project_root = self._module_root.parent
        self._last_bundle = {}  # type: Dict[str, Path]

    def _resolve_shapefile_path(self, file_path: Any) -> Path:
        """입력된 SHP 경로 문자열을 운영체제에 맞게 정규화하고 가능한 절대경로를 반환합니다.

        - Windows 스타일 백슬래시(`\\`)를 슬래시(`/`)로 치환
        - `~` 등 사용자 홈 확장
        - 상대경로일 경우: (1) 현재 작업 디렉토리, (2) 모듈 폴더, (3) 프로젝트 루트에 대해 순차적으로 탐색
        """

        if file_path is None:
            raise ValueError("Shapefile path is empty.")

        # Grasshopper 입력이 리스트/tuple인 경우 첫 요소 사용
        if isinstance(file_path, (list, tuple)):
            if not file_path:
                raise ValueError("Shapefile path list is empty.")
            file_path = file_path[0]

        raw_str = str(file_path).strip()
        if not raw_str:
            raise ValueError("Shapefile path is empty string.")

        # Windows 스타일 경로는 PureWindowsPath로 먼저 파싱 후 POSIX와 호환되도록 변환
        if "\\" in raw_str and "/" not in raw_str:
            # 예: ..\input_data\foo.shp, C:\data\foo.shp
            windows_path = PureWindowsPath(raw_str)
            candidate = Path(windows_path.as_posix())
        else:
            normalized = raw_str.replace("\\", "/")
            candidate = Path(normalized)

        candidate = candidate.expanduser()

        search_roots = []
        if candidate.is_absolute():
            search_roots.append(candidate)
        else:
            # 상대경로 그대로 시도 (현재 작업 디렉토리 기준)
            search_roots.append(Path.cwd() / candidate)
            # 모듈 위치 기준 상대경로 시도 (grasshopper/)
            search_roots.append(self._module_root / candidate)
            # 프로젝트 루트 기준 상대경로 시도 (repo 루트)
            search_roots.append(self._project_root / candidate)

        tried: List[Path] = []
        for path in search_roots:
            try:
                resolved = path.resolve(strict=False)
            except Exception:
                continue
            tried.append(resolved)
            if resolved.exists():
                return resolved

        # 존재하지 않는 경우: 진단을 위해 시도한 경로 정보를 포함한 예외를 발생시킨다.
        search_msg = (
            "\n".join(f"  - {p}" for p in tried)
            if tried
            else "  (no candidates resolved)"
        )
        raise FileNotFoundError(
            "Unable to resolve shapefile path. Tried: \n" + search_msg
        )

    def _find_dataset_file(
        self, directory: Path, stem: str, suffix: str
    ) -> Optional[Path]:
        """같은 디렉터리 내에서 대소문자를 무시하고 동일한 스템+확장자를 찾아 Path를 반환합니다."""

        expected = directory / f"{stem}{suffix}"
        if expected.exists():
            return expected

        # 대소문자 다른 파일을 탐색
        try:
            for child in directory.iterdir():
                if (
                    child.is_file()
                    and child.stem == stem
                    and child.suffix.lower() == suffix.lower()
                ):
                    return child
        except Exception:
            pass
        return None

    def _validate_shapefile_bundle(self, shp_path: Path) -> Path:
        """필수 구성요소(.shp, .dbf, .shx)가 모두 존재하는지 확인하고 실제 파일 경로를 반환합니다."""

        if shp_path.is_dir():
            raise FileNotFoundError(
                f"Shapefile path points to a directory, not a .shp file: {shp_path}"
            )

        # 확장자가 빠진 경우 .shp를 기본으로 추가
        if shp_path.suffix == "":
            shp_path = shp_path.with_suffix(".shp")

        directory = shp_path.parent
        stem = shp_path.stem

        required_exts = [".shp", ".dbf", ".shx"]
        optional_exts = [".prj", ".cpg"]

        resolved: Dict[str, Path] = {}
        missing: List[str] = []

        for ext in required_exts + optional_exts:
            found = self._find_dataset_file(directory, stem, ext)
            if found:
                resolved[ext] = found
            elif ext in required_exts:
                missing.append(str(directory / f"{stem}{ext}"))

        if missing:
            missing_paths = "\n".join(f"  - {p}" for p in missing)
            raise FileNotFoundError("Missing shapefile component(s):\n" + missing_paths)

        # 필수 파일이 모두 존재하면 캐시 후 .shp 경로 반환
        self._last_bundle = resolved
        return resolved[".shp"]

    def _resolve_output_directory(self, dir_path: Any) -> Path:
        """Shapefile 저장용 출력 디렉토리를 정규화한다.

        - Grasshopper 입력이 비어 있으면 프로젝트 루트의 output_data 디렉토리를 사용
        - Windows 스타일 경로 백슬래시 처리
        - 상대 경로는 작업 디렉토리, 모듈 디렉토리, 프로젝트 루트 순으로 탐색
        """

        default_dir = self._project_root / "output_data"

        if dir_path is None or (isinstance(dir_path, str) and not dir_path.strip()):
            dir_path = default_dir

        if isinstance(dir_path, (list, tuple)):
            dir_path = dir_path[0] if dir_path else default_dir

        raw_str = str(dir_path).strip()
        if not raw_str:
            return default_dir

        # Windows 경로 처리
        if "\\" in raw_str and "/" not in raw_str:
            candidate = Path(PureWindowsPath(raw_str).as_posix())
        else:
            candidate = Path(raw_str.replace("\\", "/"))

        candidate = candidate.expanduser()

        search_roots = []
        if candidate.is_absolute():
            search_roots.append(candidate)
        else:
            search_roots.append(Path.cwd() / candidate)
            search_roots.append(self._module_root / candidate)
            search_roots.append(self._project_root / candidate)

        tried: List[Tuple[Path, str]] = []
        for path in search_roots:
            try:
                resolved = path.resolve(strict=False)
            except Exception as e:
                tried.append((path, f"resolve error: {e}"))
                continue

            target_parent = resolved if resolved.is_dir() else resolved.parent
            if not target_parent.exists():
                tried.append((resolved, "parent missing"))
                continue

            if not os.access(str(target_parent), os.W_OK):
                tried.append((resolved, "parent not writable"))
                continue

            return resolved

        print(
            "[ShapefileManager] WARN: output directory candidates unsuitable; using default:"
        )
        for entry, reason in tried:
            print(f"  - {entry} ({reason})")

        # 기본 경로가 없다면 생성 시도에서 다시 오류를 던지도록 그대로 반환
        return default_dir

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
        road_adj = self._get_field_value(record, fields, "A23")
        min_height = self._get_field_value(record, fields, "min_height")
        max_height = self._get_field_value(record, fields, "max_height")

        if jimok == "도로" or not jimok:
            parcel = Road(boundary_region, pnu, jimok, record, hole_regions)
        else:
            parcel = Lot(
                boundary_region,
                pnu,
                jimok,
                record,
                hole_regions,
                road_adj,
                max_height,
                min_height,
            )

        # 지오메트리 전처리 후 유효한 경우에만 반환
        return parcel  # if parcel.preprocess_curve() else None

    def get_parcels_from_shapes(self, file_path: str) -> List[Parcel]:
        """
        모든 Shape로부터 Parcel 객체 리스트를 생성합니다.
        파일 경로는 이 메서드 호출 시 인자로 전달합니다.
        """
        shp_path = self._validate_shapefile_bundle(
            self._resolve_shapefile_path(file_path)
        )

        # 상세 디버그: 인코딩 순차 시도 + 내부 상태 점검
        enc_attempts = ["utf-8", "cp949", None]
        last_errors = []
        sf = None
        for enc in enc_attempts:
            try:
                path_for_reader = str(shp_path)
                if enc:
                    sf = shapefile.Reader(path_for_reader, encoding=enc)
                else:
                    sf = shapefile.Reader(path_for_reader)
                print(
                    f"[ShapefileManager] opened OK with encoding={enc} path={path_for_reader}"
                )
                # 인코딩 기록: 명시적 인코딩을 사용했다면 저장
                if enc:
                    self._encoding = enc
                break
            except Exception as e:
                last_errors.append((enc, repr(e)))
        if sf is None:
            detail = "\n".join([f"  - {enc}: {err}" for enc, err in last_errors])
            raise RuntimeError(f"Failed to open shapefile: {shp_path}\n{detail}")

        # 원시 내부 속성(필요시) 확인
        try:
            print("[DEBUG] file_path:", shp_path)
            num_shapes = getattr(sf, "numShapes", None)
            if callable(num_shapes):
                num_shapes = num_shapes()
            print("[DEBUG] numShapes:", num_shapes if num_shapes is not None else "n/a")
            print("[DEBUG] fields raw:", getattr(sf, "fields", "n/a"))
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
            prj_path = shp_path.with_suffix(".prj")
            if prj_path.exists():
                # WKT는 일반 텍스트. 인코딩은 보통 ASCII/UTF-8로 문제 없음
                self._prj_wkt = prj_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
        try:
            # .cpg 파일이 있다면 인코딩으로 활용 (명시적 인코딩 미사용 시)
            if not self._encoding:
                cpg_path = shp_path.with_suffix(".cpg")
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
        out_dir = self._resolve_output_directory(dir_path)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(
                "Unable to create output directory due to permission error: {}\n"
                "Resolved directory: {}\n"
                "원하는 저장 위치가 쓰기 가능한지 확인해 주세요.".format(e, out_dir)
            )
        except OSError as e:
            raise OSError(
                "Failed to create output directory: {}\n"
                "Resolved directory: {}\n"
                "경로를 확인하거나 다른 위치를 지정해 주세요.".format(e, out_dir)
            )

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
