"""Safe-route recommendation: candidate generation, scoring, and the
route-recommendation endpoint."""
from app.services.geo import haversine_m
from app.services.routing import candidate_routes, recommend_route
from tests.conftest import make_tourist, make_zone

_ORIGIN = (26.1000, 91.7000)
_DEST = (26.1200, 91.7200)


def _straight_line_risk_score(db):
    candidates = candidate_routes(db, _ORIGIN, _DEST)
    straight = next(
        c for c in candidates if c["points"] == [list(_ORIGIN), list(_DEST)]
    )
    return straight


def test_candidate_routes_deviate_around_a_zone_on_the_straight_line(db):
    # A high-risk zone dropped right on the direct path's midpoint.
    mid_lat = (_ORIGIN[0] + _DEST[0]) / 2
    mid_lng = (_ORIGIN[1] + _DEST[1]) / 2
    make_zone(db, name="Danger Strip", risk="high", lat=mid_lat, lng=mid_lng, d=0.004)

    candidates = candidate_routes(db, _ORIGIN, _DEST)
    assert len(candidates) == 3

    straight = next(c for c in candidates if len(c["points"]) == 2)
    recommended = candidates[0]

    # The recommended route should not be the raw straight line, and its
    # score should beat the straight line's.
    assert recommended["points"] != straight["points"]
    assert recommended["risk_score"] < straight["risk_score"]

    # The recommended route visibly deviates from the straight line: its
    # middle waypoint should sit some distance off the direct path.
    mid_waypoint = recommended["points"][1]
    dist_from_straight_mid = haversine_m(
        mid_waypoint[0], mid_waypoint[1], mid_lat, mid_lng
    )
    assert dist_from_straight_mid > 50


def test_candidate_routes_sorted_best_first(db):
    make_zone(db, name="Danger Strip", risk="restricted",
              lat=(_ORIGIN[0] + _DEST[0]) / 2, lng=(_ORIGIN[1] + _DEST[1]) / 2, d=0.004)
    candidates = candidate_routes(db, _ORIGIN, _DEST)
    scores = [c["risk_score"] for c in candidates]
    assert scores == sorted(scores)


def test_degenerate_same_origin_and_destination_returns_single_zero_length_route(db):
    candidates = candidate_routes(db, _ORIGIN, _ORIGIN)
    assert len(candidates) == 1
    assert candidates[0]["length_km"] == 0.0
    assert candidates[0]["risk_score"] >= 0.0


def test_all_candidates_have_plausible_lengths(db):
    candidates = candidate_routes(db, _ORIGIN, _DEST)
    direct_km = haversine_m(*_ORIGIN, *_DEST) / 1000.0
    for c in candidates:
        assert c["length_km"] > 0
        # A small lateral offset shouldn't blow the route up to many times
        # the direct distance.
        assert c["length_km"] < direct_km * 3


def test_recommend_route_tags_risk_level_and_picks_lowest_risk(db):
    make_zone(db, name="Danger Strip", risk="restricted",
              lat=(_ORIGIN[0] + _DEST[0]) / 2, lng=(_ORIGIN[1] + _DEST[1]) / 2, d=0.004)
    result = recommend_route(db, _ORIGIN, _DEST)
    assert "recommended" in result
    assert "candidates" in result
    assert len(result["candidates"]) == 3
    for c in result["candidates"]:
        assert c["risk_level"] in {"low", "medium", "high", "restricted"}
    assert result["recommended"] == result["candidates"][0]


def test_recommend_route_with_no_zones_is_all_low_risk(db):
    result = recommend_route(db, _ORIGIN, _DEST)
    for c in result["candidates"]:
        assert c["risk_level"] == "low"
        assert c["risk_score"] == 0.0


# ------------------------------------------------------------------- endpoint


def test_route_recommendation_endpoint_admin_success(client, admin_headers, db):
    t = make_tourist(db, lat=_ORIGIN[0], lng=_ORIGIN[1])
    r = client.get(
        f"/api/tourists/{t.id}/route-recommendation",
        params={"dest_lat": _DEST[0], "dest_lng": _DEST[1]},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tourist_id"] == t.id
    assert "recommended" in body
    assert len(body["candidates"]) == 3


def test_route_recommendation_endpoint_self_success(client, tourist_headers, tourist_user):
    t = tourist_user.tourist_id
    # tourist_user fixture's underlying Tourist row already has a location
    # from make_tourist's defaults -- just call the endpoint as that tourist.
    r = client.get(
        f"/api/tourists/{t}/route-recommendation",
        params={"dest_lat": _DEST[0], "dest_lng": _DEST[1]},
        headers=tourist_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["tourist_id"] == t


def test_route_recommendation_endpoint_400_when_no_known_location(client, admin_headers, db):
    t = make_tourist(db)
    t.last_lat = None
    t.last_lng = None
    db.commit()
    r = client.get(
        f"/api/tourists/{t.id}/route-recommendation",
        params={"dest_lat": _DEST[0], "dest_lng": _DEST[1]},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_route_recommendation_endpoint_403_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Other Tourist", doc="XXXX-XXXX-0099")
    r = client.get(
        f"/api/tourists/{other.id}/route-recommendation",
        params={"dest_lat": _DEST[0], "dest_lng": _DEST[1]},
        headers=tourist_headers,
    )
    assert r.status_code == 403
