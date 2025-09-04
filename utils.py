# -*- coding: utf-8 -*-
from typing import List, Tuple, Any, Optional, Union
import functools
import Rhino
import Rhino.Geometry as geo
import ghpythonlib.components as ghcomp

from constants import TOL, ROUNDING_PRECISION, BIGNUM, OP_TOL, CLIPPER_TOL

# Type Hinting
CurveLike = Union[geo.Curve, List[geo.Curve]]


def convert_io_to_list(func):
    """인풋과 아웃풋을 리스트로 만들어주는 데코레이터"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        new_args = []
        for arg in args:
            if isinstance(arg, geo.Curve):
                arg = [arg]
            new_args.append(arg)

        result = func(*new_args, **kwargs)
        if isinstance(result, geo.Curve):
            result = [result]
        if hasattr(result, "__dict__"):
            for key, values in result.__dict__.items():
                if isinstance(values, geo.Curve):
                    setattr(result, key, [values])
        return result

    return wrapper


# ==============================================================================
# 1. 코어 지오메트리 유틸리티 (Core Geometry Utilities)
# ==============================================================================


def get_distance_between_points(point_a: geo.Point3d, point_b: geo.Point3d) -> float:
    """두 점 사이의 거리를 계산합니다."""
    return round(point_a.DistanceTo(point_b), ROUNDING_PRECISION)


def get_distance_between_point_and_curve(point: geo.Point3d, curve: geo.Curve) -> float:
    """점과 커브 사이의 최단 거리를 계산합니다."""
    _, param = curve.ClosestPoint(point)
    dist = point.DistanceTo(curve.PointAt(param))
    return round(dist, ROUNDING_PRECISION)


def get_distance_between_curves(curve_a: geo.Curve, curve_b: geo.Curve) -> float:
    """두 커브 사이의 최소 거리를 계산합니다."""
    _, pt_a, pt_b = curve_a.ClosestPoints(curve_b)
    dist = pt_a.DistanceTo(pt_b)
    return round(dist, ROUNDING_PRECISION)


def get_vector_from_pts(pt_a: geo.Point3d, pt_b: geo.Point3d) -> geo.Vector3d:
    """두 점 사이의 벡터를 계산합니다."""
    return geo.Vector3d(pt_b.X - pt_a.X, pt_b.Y - pt_a.Y, pt_b.Z - pt_a.Z)


def get_vertices(curve: geo.Curve) -> List[geo.Point3d]:
    """커브의 모든 정점(Vertex)들을 추출합니다."""
    if not curve:
        return []
    vertices = [curve.PointAt(curve.SpanDomain(i)[0]) for i in range(curve.SpanCount)]
    if not curve.IsClosed:
        vertices.append(curve.PointAtEnd)
    return vertices


def move_curve(curve: geo.Curve, vector: geo.Vector3d) -> geo.Curve:
    """커브를 주어진 벡터만큼 이동시킨 복사본을 반환합니다."""
    moved_curve = curve.Duplicate()
    moved_curve.Translate(vector)
    return moved_curve


def explode_curve(curve: geo.Curve) -> List[geo.Curve]:
    """커브를 분할하여 개별 세그먼트 리스트로 반환합니다."""
    if not curve:
        return []
    if isinstance(curve, geo.PolyCurve):
        return list(curve.DuplicateSegments())

    segments = []
    if curve.SpanCount > 0:
        for i in range(curve.SpanCount):
            sub_curve = curve.Trim(curve.SpanDomain(i))
            if sub_curve:
                segments.append(sub_curve)
    elif curve.IsLinear():
        segments.append(curve.Duplicate())

    return segments


def get_pts_by_length(
    crv: geo.Curve, length: float, include_start: bool = False
) -> List[geo.Point3d]:
    """커브를 주어진 길이로 나누는 점들을 구합니다."""
    params = crv.DivideByLength(length, include_start)
    if not params:
        return []
    return [crv.PointAt(param) for param in params]


# ==============================================================================
# 2. 고급 지오메트리 연산 (Advanced Geometry Operations)
# ==============================================================================


def has_intersection(
    curve_a: geo.Curve,
    curve_b: geo.Curve,
    plane: geo.Plane = geo.Plane.WorldXY,
    tol: float = TOL,
) -> bool:
    """두 커브가 교차하는지 여부를 확인합니다."""
    return geo.Curve.PlanarCurveCollision(curve_a, curve_b, plane, tol)


def get_intersection_points(
    curve_a: geo.Curve, curve_b: geo.Curve, tol: float = TOL
) -> List[geo.Point3d]:
    """두 커브 사이의 교차점을 계산합니다."""
    intersections = geo.Intersect.Intersection.CurveCurve(curve_a, curve_b, tol, tol)
    if not intersections:
        return []
    return [event.PointA for event in intersections if event.IsPointAValid]


def has_region_intersection(
    region_a: geo.Curve, region_b: geo.Curve, tol: float = TOL
) -> bool:
    """두 닫힌 영역 커브가 교차(겹침 포함)하는지 확인합니다."""
    relationship = geo.Curve.PlanarClosedCurveRelationship(
        region_a, region_b, geo.Plane.WorldXY, tol
    )
    return relationship != geo.RegionContainment.Disjoint


def is_region_inside(
    inner_region: geo.Curve, outer_region: geo.Curve, tol: float = TOL
) -> bool:
    """내부 영역이 외부 영역에 포함되는지 확인합니다."""
    relationship = geo.Curve.PlanarClosedCurveRelationship(
        inner_region, outer_region, geo.Plane.WorldXY, tol
    )

    return relationship == geo.RegionContainment.AInsideB


def get_overlapped_curves(curve_a: geo.Curve, curve_b: geo.Curve) -> List[geo.Curve]:
    """두 커브가 겹치는 구간의 커브들을 반환합니다."""
    if not has_intersection(curve_a, curve_b) or not ghcomp:
        return []

    intersection_points = get_intersection_points(curve_a, curve_b)
    explode_result = ghcomp.Explode(curve_a, True)
    explode_points = (
        explode_result.vertices + intersection_points
        if explode_result
        else intersection_points
    )

    if not explode_points:
        return []

    params = [ghcomp.CurveClosestPoint(pt, curve_a).parameter for pt in explode_points]
    shatter_result = ghcomp.Shatter(curve_a, params)

    if not shatter_result:
        return []

    overlapped_segments = [
        seg for seg in shatter_result if has_intersection(seg, curve_b)
    ]
    if not overlapped_segments:
        return []

    return geo.Curve.JoinCurves(overlapped_segments)


def get_overlapped_length(curve_a: geo.Curve, curve_b: geo.Curve) -> float:
    """두 커브가 겹치는 총 길이를 계산합니다."""
    overlapped_curves = get_overlapped_curves(curve_a, curve_b)
    if not overlapped_curves:
        return 0.0
    return sum(crv.GetLength() for crv in overlapped_curves)


class Offset:
    class _OffsetResult:
        def __init__(self):
            self.contour: Optional[List[geo.Curve]] = None
            self.holes: Optional[List[geo.Curve]] = None

    @convert_io_to_list
    def polyline_offset(
        self,
        crvs: List[geo.Curve],
        dists: List[float],
        miter: int = BIGNUM,
        closed_fillet: int = 2,
        open_fillet: int = 2,
        tol: float = Rhino.RhinoMath.ZeroTolerance,
    ) -> _OffsetResult:
        """
        Args:
            crv (_type_): _description_
            dists (_type_): _description_
            miter : miter
            closed_fillet : 0 = round, 1 = square, 2 = miter
            open_fillet : 0 = round, 1 = square, 2 = butt

        Returns:
            _type_: _OffsetResult
        """
        if not crvs:
            raise ValueError("No Curves to offset")

        plane = geo.Plane(geo.Point3d(0, 0, crvs[0].PointAtEnd.Z), geo.Vector3d.ZAxis)
        result = ghcomp.ClipperComponents.PolylineOffset(
            crvs,
            dists,
            plane,
            tol,
            closed_fillet,
            open_fillet,
            miter,
        )

        polyline_offset_result = Offset._OffsetResult()
        for name in ("contour", "holes"):
            setattr(polyline_offset_result, name, result[name])
        return polyline_offset_result


def offset_regions_inward(
    regions: Union[geo.Curve, List[geo.Curve]], dist: float, miter: int = BIGNUM
) -> List[geo.Curve]:
    """영역 커브를 안쪽으로 offset 한다.
    단일커브나 커브리스트 관계없이 커브 리스트로 리턴한다.
    Args:
        region: offset할 대상 커브
        dist: offset할 거리

    Returns:
        offset 후 커브
    """

    if not dist:
        return regions
    result = Offset().polyline_offset(regions, dist, miter).holes

    if isinstance(regions, geo.Curve):
        regions = [regions]

    if len(result) < 2:
        return result

    filtered = [
        crv for crv in result if any(is_region_inside(crv, reg) for reg in regions)
    ]
    return filtered


def offset_regions_outward(
    regions: Union[geo.Curve, List[geo.Curve]], dist: float, miter: int = BIGNUM
) -> List[geo.Curve]:
    """영역 커브를 바깥쪽으로 offset 한다.
    단일커브나 커브리스트 관계없이 커브 리스트로 리턴한다.
    Args:
        region: offset할 대상 커브
        dist: offset할 거리
    returns:
        offset 후 커브
    """
    if isinstance(regions, geo.Curve):
        regions = [regions]

    return [offset_region_outward(region, dist, miter) for region in regions]


def offset_region_outward(
    region: geo.Curve, dist: float, miter: float = BIGNUM
) -> geo.Curve:
    """영역 커브를 바깥쪽으로 offset 한다.
    단일 커브를 받아서 단일 커브로 리턴한다.
    Args:
        region: offset할 대상 커브
        dist: offset할 거리

    Returns:
        offset 후 커브
    """

    if not dist:
        return region
    if not isinstance(region, geo.Curve):
        raise ValueError("region must be curve")
    return Offset().polyline_offset(region, dist, miter).contour[0]


class RegionBool:
    @convert_io_to_list
    def _polyline_boolean(
        self, crvs0, crvs1, boolean_type=None, plane=None, tol=CLIPPER_TOL
    ):
        # type: (List[geo.Curve], List[geo.Curve], int, geo.Plane, float) -> List[geo.Curve]
        if not crvs0 or not crvs1:
            raise ValueError("Check input values")
        result = ghcomp.ClipperComponents.PolylineBoolean(
            crvs0, crvs1, boolean_type, plane, tol
        )

        # 결과는 IronPython.Runtime.List (파이썬 list처럼 동작) 이거나 단일 커브일 수 있으므로 통일해서 list로 반환
        if not result:
            return []

        # IronPython.Runtime.List, System.Collections.Generic.List, tuple 등 반복 가능한 결과를 모두 처리
        if isinstance(result, geo.Curve):
            # 단일 커브 객체
            result = [result]
        else:
            try:
                # IEnumerable / IronPython.Runtime.List / tuple / System.Collections.Generic.List 모두 list() 시도로 통일
                result = [crv for crv in list(result) if crv]
            except TypeError:
                # 반복 불가능한 단일 객체인 예외 상황
                result = [result]

        return result

    def polyline_boolean_union(self, crvs0, crvs1, plane=None, tol=CLIPPER_TOL):
        # type: (Union[geo.Curve, List[geo.Curve]], Union[geo.Curve, List[geo.Curve]], geo.Plane, float) -> List[geo.Curve]
        return self._polyline_boolean(crvs0, crvs1, 1, plane, tol)


def get_union_regions(regions: List[geo.Curve] = None) -> List[geo.Curve]:
    """주어진 영역 커브들의 합집합을 구합니다.
    Args:
        regions: 합집합을 구할 영역 커브들
    Returns:
        합집합 결과 커브들
    """
    if not regions:
        return []

    if len(regions) == 1:
        return regions

    union_result = list(geo.Curve.CreateBooleanUnion(regions, TOL))
    if union_result:
        return union_result

    union_result = regions[0]
    for region in regions[1:]:
        union_result = RegionBool().polyline_boolean_union(union_result, region)

    if not isinstance(union_result, list):
        union_result = [union_result]

    return union_result
