"""Tests for HydrologyService graph construction and connectivity queries."""

from unittest.mock import patch

from src.models.hydrology import HydroBarrier, StreamSegment
from src.services.hydrology import HydrologyService, _build_summary, _can_pass

# ── test network ──────────────────────────────────────────────────────────────
# Network shape (flow = upstream → downstream):
#
#   A ──Seg1──► B ──Seg2──► C
#                  └──Seg3──► D  (Falls barrier on Seg3)
#   E ──Seg4──► F            (unverified, bidirectional)
#
# Nodes: A=-79.5,43.5  B=-79.48,43.51  C=-79.46,43.52
#        D=-79.47,43.505  E=-79.49,43.495  F=-79.5,43.485

_SEGMENTS = [
    StreamSegment(
        ogf_id=10001, watercourse_type="Stream", name="Bronte Creek",
        flow_verified=True, permanency="Permanent", flow_classification="Primary",
        length_m=2500.0,
        geom_wkt="LINESTRING (-79.5 43.5, -79.49 43.505, -79.48 43.51)",
        start_node="-79.5,43.5", end_node="-79.48,43.51",
    ),
    StreamSegment(
        ogf_id=10002, watercourse_type="Stream", name="Bronte Creek",
        flow_verified=True, permanency="Permanent", flow_classification="Primary",
        length_m=2500.0,
        geom_wkt="LINESTRING (-79.48 43.51, -79.47 43.515, -79.46 43.52)",
        start_node="-79.48,43.51", end_node="-79.46,43.52",
    ),
    StreamSegment(
        ogf_id=10003, watercourse_type="Stream", name=None,
        flow_verified=True, permanency="Permanent", flow_classification="Primary",
        length_m=1250.0,
        geom_wkt="LINESTRING (-79.48 43.51, -79.475 43.5075, -79.47 43.505)",
        start_node="-79.48,43.51", end_node="-79.47,43.505",
    ),
    StreamSegment(
        ogf_id=10004, watercourse_type="Stream", name=None,
        flow_verified=False, permanency="Permanent", flow_classification="Primary",
        length_m=1500.0,
        geom_wkt="LINESTRING (-79.49 43.495, -79.5 43.485)",
        start_node="-79.49,43.495", end_node="-79.5,43.485",
    ),
]

_FALLS_BARRIER = HydroBarrier(
    ogf_id=20001, barrier_type="Falls",
    geom_wkt="POINT (-79.475 43.5075)",
    nearest_segment_ogf_id=10003, snap_distance_m=0.0,
)

_SLB_BARRIER = HydroBarrier(
    ogf_id=20002, barrier_type="Sea Lamprey Barrier",
    geom_wkt="POINT (-79.47 43.515)",
    nearest_segment_ogf_id=10002, snap_distance_m=0.0,
)


def _make_service(segments=None, barriers=None) -> HydrologyService:
    svc = HydrologyService.__new__(HydrologyService)
    svc._db = None
    svc._graph = None
    svc._seg_index = {}
    segs = _SEGMENTS if segments is None else segments
    bars = [] if barriers is None else barriers
    with patch("src.services.hydrology._load_segments", return_value=segs), \
         patch("src.services.hydrology._load_barriers", return_value=bars):
        svc._ensure_graph()
    return svc


# ── graph construction ────────────────────────────────────────────────────────

def test_verified_segment_creates_directed_edge():
    svc = _make_service()
    G = svc._graph
    assert G.has_edge("-79.5,43.5", "-79.48,43.51")
    assert not G.has_edge("-79.48,43.51", "-79.5,43.5")


def test_unverified_segment_creates_bidirectional_edges():
    svc = _make_service()
    G = svc._graph
    assert G.has_edge("-79.49,43.495", "-79.5,43.485")
    assert G.has_edge("-79.5,43.485", "-79.49,43.495")


def test_barrier_assigned_to_nearest_segment():
    svc = _make_service(barriers=[_FALLS_BARRIER])
    G = svc._graph
    # Seg3 goes from B to D; Falls barrier is on Seg3 (ogf_id 10003)
    edge = G["-79.48,43.51"]["-79.47,43.505"]
    assert edge["barrier_type"] == "Falls"


def test_node_count():
    svc = _make_service()
    G = svc._graph
    # Nodes: A, B, C, D, E, F = 6 unique nodes
    assert G.number_of_nodes() == 6


# ── upstream / downstream traversal ──────────────────────────────────────────

def test_upstream_of_node_b_returns_seg1():
    svc = _make_service()
    # B is at (-79.48, 43.51); upstream is A via Seg1
    result = svc.upstream_of(43.51, -79.48, max_km=50)
    ogf_ids = {r["ogf_id"] for r in result}
    assert 10001 in ogf_ids  # Seg1 (A→B) is upstream of B


def test_downstream_of_node_b_returns_seg2_and_seg3():
    svc = _make_service()
    result = svc.downstream_of(43.51, -79.48, max_km=50)
    ogf_ids = {r["ogf_id"] for r in result}
    assert 10002 in ogf_ids  # Seg2 (B→C)
    assert 10003 in ogf_ids  # Seg3 (B→D)


def test_upstream_results_sorted_by_distance():
    svc = _make_service()
    result = svc.upstream_of(43.52, -79.46, max_km=50)  # start from C
    dists = [r["distance_km"] for r in result]
    assert dists == sorted(dists)


def test_max_km_limits_traversal():
    svc = _make_service()
    # From A, Seg1 = 2.5km to B, Seg2 = 5km to C; limit to 3km
    result = svc.downstream_of(43.5, -79.5, max_km=3.0)
    ogf_ids = {r["ogf_id"] for r in result}
    assert 10001 in ogf_ids   # 2.5km — within limit
    assert 10002 not in ogf_ids  # 5km total — exceeds limit


# ── reachable_from with barrier filtering ────────────────────────────────────

def test_reachable_from_prunes_at_falls_for_all_species():
    svc = _make_service(barriers=[_FALLS_BARRIER])
    # From B, Seg3 has a Falls barrier → D should be unreachable
    result = svc.reachable_from(43.51, -79.48, species="Brook Trout", max_km=50)
    ogf_ids = {r["ogf_id"] for r in result}
    assert 10003 not in ogf_ids  # Seg3 blocked by Falls
    assert 10002 in ogf_ids      # Seg2 is free


def test_reachable_from_sea_lamprey_barrier_blocks_only_lamprey():
    svc = _make_service(barriers=[_SLB_BARRIER])
    # SLB is on Seg2 (B→C); lamprey cannot pass, trout can
    trout_result = svc.reachable_from(43.51, -79.48, species="Brook Trout", max_km=50)
    lamprey_result = svc.reachable_from(43.51, -79.48, species="Sea Lamprey", max_km=50)

    trout_ogf_ids = {r["ogf_id"] for r in trout_result}
    lamprey_ogf_ids = {r["ogf_id"] for r in lamprey_result}

    assert 10002 in trout_ogf_ids     # trout passes SLB
    assert 10002 not in lamprey_ogf_ids  # lamprey blocked


# ── connected_tributaries ────────────────────────────────────────────────────

def test_connected_tributaries_finds_unnamed_trib():
    svc = _make_service()
    tribs = svc.connected_tributaries("Bronte Creek")
    trib_ogf_ids = {t["ogf_id"] for t in tribs}
    assert 10003 in trib_ogf_ids  # unnamed tributary at B


def test_connected_tributaries_excludes_main_stem():
    svc = _make_service()
    tribs = svc.connected_tributaries("Bronte Creek")
    trib_ogf_ids = {t["ogf_id"] for t in tribs}
    assert 10001 not in trib_ogf_ids
    assert 10002 not in trib_ogf_ids


def test_connected_tributaries_unknown_name_returns_empty():
    svc = _make_service()
    tribs = svc.connected_tributaries("Nonexistent River")
    assert tribs == []


# ── connectivity_summary ──────────────────────────────────────────────────────

def test_connectivity_summary_sentence_no_observations():
    svc = _make_service()
    result = svc.connectivity_summary(43.51, -79.48, "Brook Trout", confirmed_observations=[])
    assert "No confirmed" in result.summary_sentence
    assert result.connected_observations == []
    assert result.nearest_barrier is None


def test_connectivity_summary_connected_observation():
    svc = _make_service()
    obs = [{"lat": 43.52, "lng": -79.46, "place_guess": "Downstream Node C"}]
    result = svc.connectivity_summary(43.5, -79.5, "Brook Trout", confirmed_observations=obs)
    assert result.connected_observations != []
    sentence = result.summary_sentence.lower()
    assert "brook trout" in sentence
    assert result.connected_observations[0]["distance_km"] > 0


def test_connectivity_summary_barrier_on_path():
    svc = _make_service(barriers=[_FALLS_BARRIER])
    # Observation at D (-79.47, 43.505), query at C (-79.46, 43.52)
    # Path C→B→D crosses the Falls on Seg3
    obs = [{"lat": 43.505, "lng": -79.47, "place_guess": "Tributary D"}]
    result = svc.connectivity_summary(43.52, -79.46, "Brook Trout", confirmed_observations=obs)
    # The barrier should be detected on the path
    sentence = result.summary_sentence.lower()
    assert result.nearest_barrier == "Falls" or "falls" in sentence or "waterfall" in sentence


def test_connectivity_summary_no_graph_data():
    svc = _make_service(segments=[])
    result = svc.connectivity_summary(43.51, -79.48, "Brook Trout", confirmed_observations=[])
    assert "No stream network data" in result.summary_sentence


# ── barrier passability ───────────────────────────────────────────────────────

def test_falls_impassable_for_all():
    assert _can_pass("Brook Trout", "Falls") is False
    assert _can_pass("Sea Lamprey", "Falls") is False
    assert _can_pass(None, "Falls") is False


def test_rocks_passable_for_all():
    assert _can_pass("Brook Trout", "Rocks") is True
    assert _can_pass("Johnny Darter", "Rocks") is True
    assert _can_pass(None, "Rocks") is True


def test_sea_lamprey_barrier_blocks_only_lamprey():
    assert _can_pass("Sea Lamprey", "Sea Lamprey Barrier") is False
    assert _can_pass("Brook Trout", "Sea Lamprey Barrier") is True
    assert _can_pass("Rainbow Trout", "Sea Lamprey Barrier") is True
    assert _can_pass("Smallmouth Bass", "Sea Lamprey Barrier") is True
    assert _can_pass(None, "Sea Lamprey Barrier") is True


def test_rapids_passable_for_strong_swimmers():
    assert _can_pass("Brook Trout", "Rapids") is True
    assert _can_pass("Salmon", "Rapids") is True
    assert _can_pass("Smallmouth Bass", "Rapids") is True


def test_rapids_impassable_for_microfishing_targets():
    assert _can_pass("Johnny Darter", "Rapids") is False
    assert _can_pass("Common Shiner", "Rapids") is False
    assert _can_pass("Northern Madtom", "Rapids") is False


# ── summary sentence format ───────────────────────────────────────────────────

def test_build_summary_no_observations():
    sentence = _build_summary("Brook Trout", [], None)
    assert "No confirmed" in sentence
    assert "Brook Trout" in sentence or "brook trout" in sentence.lower()


def test_build_summary_passable_connection():
    connected = [{"place_guess": "Bronte Creek", "distance_km": 2.3, "blocking_barrier": None}]
    sentence = _build_summary("Brook Trout", connected, None)
    assert "2.3" in sentence
    assert "Bronte Creek" in sentence
    assert "intact" in sentence or "no barriers" in sentence.lower()


def test_build_summary_blocked_connection():
    connected = [{"place_guess": "Bronte Creek", "distance_km": 4.1, "blocking_barrier": "Falls"}]
    sentence = _build_summary("Brook Trout", connected, "Falls")
    assert "4.1" in sentence
    assert "waterfall" in sentence.lower() or "falls" in sentence.lower()
