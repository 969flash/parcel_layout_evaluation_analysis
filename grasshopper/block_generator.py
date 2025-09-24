# r: pyshp, geopandas, networkx

import Rhino.Geometry as geo
import geopandas as gpd
import networkx as nx
from shapely.geometry import Polygon
from typing import List, Optional, Any

# units.py에서 units.Lot과 units.Block 클래스를 임포트했다고 가정

import units
import utils
import importlib

importlib.reload(utils)
importlib.reload(units)


class BlockGenerator:
    def __init__(self):
        pass

    def generate(self, lots: List[units.Lot]) -> List[units.Block]:
        """주어진 units.Lot 리스트로부터 units.Block 객체 리스트를 생성합니다."""

        lots_to_process = [p for p in lots if p.__class__.__name__ == "Lot"]
        return self._create_blocks_from_lots(lots_to_process)

    def _rhino_curve_to_shapely_polygon(
        self, region_curve: geo.Curve, hole_curves: Optional[List[geo.Curve]] = None
    ) -> Optional[Polygon]:
        """Rhino 커브를 utils.get_vertices 기반으로 Shapely Polygon으로 변환.
        - 커브 Span 기준 정점 추출
        - 중복 제거
        - 닫힌 커브 미보장 시 첫/끝 점 강제 닫기
        """
        if not region_curve or not region_curve.IsValid:
            return None

        verts = utils.get_vertices(region_curve)
        if not verts:
            return None

        # 중복 제거(순서 유지)
        shell_pts: List[tuple] = []
        seen = set()
        for pt in verts:
            key = (round(pt.X, 9), round(pt.Y, 9))
            if key in seen:
                continue
            seen.add(key)
            shell_pts.append((pt.X, pt.Y))

        # 닫힘 보장
        if len(shell_pts) >= 3 and shell_pts[0] != shell_pts[-1]:
            shell_pts.append(shell_pts[0])

        if len(shell_pts) < 4:  # 시작=끝 포함 최소 4
            return None

        holes_coords: List[List[tuple]] = []
        if hole_curves:
            for h in hole_curves:
                if not h or not h.IsValid:
                    continue
                h_verts = utils.get_vertices(h)
                if not h_verts:
                    continue
                h_seen = set()
                h_pts: List[tuple] = []
                for p in h_verts:
                    k = (round(p.X, 9), round(p.Y, 9))
                    if k in h_seen:
                        continue
                    h_seen.add(k)
                    h_pts.append((p.X, p.Y))
                if len(h_pts) >= 3 and h_pts[0] != h_pts[-1]:
                    h_pts.append(h_pts[0])
                if len(h_pts) >= 4:
                    holes_coords.append(h_pts)

        try:
            return Polygon(shell_pts, holes_coords)
        except Exception:
            return None

    def _create_blocks_from_lots(self, lots: List[units.Lot]) -> List[units.Block]:
        """
        units.Lot 리스트를 받아 공간적으로 인접한 units.Lot들을 그룹화하여 units.Block 리스트를 생성합니다.
        """
        if not lots:
            print("No valid lots to process.")
            return []

        # 나중에 units.Lot 객체를 쉽게 찾기 위해 PNU를 키로 하는 딕셔너리 생성
        lot_map = {lot.pnu: lot for lot in lots}

        # GeoDataFrame 생성을 위한 데이터 준비
        geometries = []
        pnu_list = []
        for lot in lots:
            polygon = self._rhino_curve_to_shapely_polygon(lot.region, lot.hole_regions)
            if polygon:
                geometries.append(polygon)
                pnu_list.append(lot.pnu)

        if not pnu_list:
            print(" NO PNU ")
            # 유효한 지오메트리가 하나도 없는 경우
            return [units.Block(lots=[lot]) for lot in lots]

        # GeoDataFrame 생성 (공간 인덱스가 자동으로 만들어짐)
        gdf = gpd.GeoDataFrame({"pnu": pnu_list, "geometry": geometries})
        print(len(gdf), "valid geometries created for lots.")

        # 1. sjoin으로 교차하거나 접하는 모든 units.Lot 쌍을 빠르게 찾기
        intersecting_gdf = gpd.sjoin(gdf, gdf, how="inner", predicate="intersects")

        # 2. 결과에서 자기 자신과의 쌍은 제외
        intersecting_gdf = intersecting_gdf[
            intersecting_gdf.pnu_left != intersecting_gdf.pnu_right
        ]

        # 3. NetworkX 그래프 생성을 위한 엣지(연결 관계) 리스트 만들기
        edges = set()
        for _, row in intersecting_gdf.iterrows():
            pair = tuple(sorted((row["pnu_left"], row["pnu_right"])))
            edges.add(pair)

        # 4. 그래프를 만들고 '연결된 요소(뭉치)' 찾기
        G = nx.Graph()
        G.add_nodes_from(
            pnu_list
        )  # 모든 units.Lot을 노드로 추가 (연결 없는 units.Lot도 포함)
        G.add_edges_from(edges)

        clusters = list(nx.connected_components(G))

        # 5. 찾은 클러스터(PNU 묶음)를 기반으로 units.Block 객체 생성
        blocks = []
        for pnu_group in clusters:
            cluster_lots = [lot_map[pnu] for pnu in pnu_group]
            blocks.append(units.Block(lots=cluster_lots))

        return blocks
