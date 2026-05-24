"""Tests for hydrology Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models.hydrology import ConnectivityResult, HydroBarrier, StreamSegment


def test_stream_segment_minimal():
    seg = StreamSegment(
        ogf_id=10001,
        watercourse_type="Stream",
        flow_verified=True,
        permanency="Permanent",
        length_m=2500.0,
        geom_wkt="LINESTRING (-79.5 43.5, -79.48 43.51)",
        start_node="-79.5,43.5",
        end_node="-79.48,43.51",
    )
    assert seg.ogf_id == 10001
    assert seg.name is None
    assert seg.jurisdiction == "CA-ON"
    assert seg.flow_verified is True


def test_stream_segment_with_name():
    seg = StreamSegment(
        ogf_id=10002,
        watercourse_type="Stream",
        name="Bronte Creek",
        flow_verified=True,
        permanency="Permanent",
        flow_classification="Primary",
        length_m=1250.0,
        geom_wkt="LINESTRING (-79.48 43.51, -79.46 43.52)",
        start_node="-79.48,43.51",
        end_node="-79.46,43.52",
    )
    assert seg.name == "Bronte Creek"
    assert seg.flow_classification == "Primary"


def test_stream_segment_virtual_flow():
    seg = StreamSegment(
        ogf_id=10003,
        watercourse_type="Virtual Flow",
        flow_verified=False,
        permanency="Permanent",
        length_m=500.0,
        geom_wkt="LINESTRING (-79.4 43.5, -79.38 43.51)",
        start_node="-79.4,43.5",
        end_node="-79.38,43.51",
    )
    assert seg.watercourse_type == "Virtual Flow"
    assert seg.flow_verified is False


def test_stream_segment_requires_ogf_id():
    with pytest.raises(ValidationError):
        StreamSegment(
            watercourse_type="Stream",
            flow_verified=True,
            permanency="Permanent",
            length_m=100.0,
            geom_wkt="LINESTRING (0 0, 1 1)",
            start_node="0,0",
            end_node="1,1",
        )


def test_hydro_barrier_falls():
    b = HydroBarrier(
        ogf_id=20001,
        barrier_type="Falls",
        geom_wkt="POINT (-79.475 43.5075)",
        nearest_segment_ogf_id=10003,
        snap_distance_m=0.0,
    )
    assert b.barrier_type == "Falls"
    assert b.nearest_segment_ogf_id == 10003
    assert b.jurisdiction == "CA-ON"


def test_hydro_barrier_sea_lamprey():
    b = HydroBarrier(
        ogf_id=20002,
        barrier_type="Sea Lamprey Barrier",
        geom_wkt="POINT (-79.47 43.515)",
        nearest_segment_ogf_id=10002,
        snap_distance_m=5.0,
    )
    assert b.barrier_type == "Sea Lamprey Barrier"


def test_hydro_barrier_no_snap():
    b = HydroBarrier(
        ogf_id=20003,
        barrier_type="Rapids",
        geom_wkt="POINT (-80.0 44.0)",
    )
    assert b.nearest_segment_ogf_id is None
    assert b.snap_distance_m is None


def test_connectivity_result_fields():
    r = ConnectivityResult(
        query_lat=43.505,
        query_lon=-79.49,
        species="Brook Trout",
        connected_observations=[],
        nearest_barrier=None,
        summary_sentence="No confirmed Brook Trout observations found on connected reaches.",
    )
    assert r.species == "Brook Trout"
    assert r.nearest_barrier is None
    assert "Brook Trout" in r.summary_sentence
