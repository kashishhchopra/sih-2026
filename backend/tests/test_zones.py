"""Zone CRUD and polygon validation."""
import pytest


def _zone(**over):
    base = {
        "name": "Test Zone", "risk_level": "high",
        "polygon": [[26.1, 91.7], [26.1, 91.8], [26.2, 91.8], [26.2, 91.7]],
        "crime_index": 60.0, "description": "test",
    }
    base.update(over)
    return base


def test_create_and_list_zone(client, admin_headers):
    r = client.post("/api/zones", json=_zone(), headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["source"] == "manual"
    assert len(client.get("/api/zones", headers=admin_headers).json()) == 1


def test_tourists_may_read_zones(client, tourist_headers):
    """Tourists need zone geometry to render geofence warnings on their map."""
    assert client.get("/api/zones", headers=tourist_headers).status_code == 200


def test_tourists_may_not_create_zones(client, tourist_headers):
    assert client.post("/api/zones", json=_zone(),
                       headers=tourist_headers).status_code == 403


def test_delete_zone(client, admin_headers):
    zid = client.post("/api/zones", json=_zone(), headers=admin_headers).json()["id"]
    assert client.delete(f"/api/zones/{zid}", headers=admin_headers).status_code == 204
    assert client.delete(f"/api/zones/{zid}", headers=admin_headers).status_code == 404


@pytest.mark.parametrize("polygon", [
    [[26.1, 91.7], [26.1, 91.8]],                    # too few vertices
    [[26.1, 91.7, 5], [26.1, 91.8], [26.2, 91.8]],   # 3-element vertex
    [[200.0, 91.7], [26.1, 91.8], [26.2, 91.8]],     # lat out of range
])
def test_invalid_polygon_rejected(client, admin_headers, polygon):
    assert client.post("/api/zones", json=_zone(polygon=polygon),
                       headers=admin_headers).status_code == 422


@pytest.mark.parametrize("risk", ["extreme", "", "HIGH"])
def test_invalid_risk_level_rejected(client, admin_headers, risk):
    assert client.post("/api/zones", json=_zone(risk_level=risk),
                       headers=admin_headers).status_code == 422
