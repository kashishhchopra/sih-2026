"""Permit & E-Pass Automation (services/permit.py, /permits/*, /tourists/{id}/permits).

The core invariant under test: this app never claims to submit a permit
application to a government system, never auto-approves, and always hands
back the real official portal for the tourist to finish on -- see the
honesty rule documented in services/permit.py's module docstring.
"""
from app.models.tourist import Tourist
from tests.conftest import make_tourist


def test_permit_types_include_real_portal_links(client, admin_headers):
    r = client.get("/api/permits/types", headers=admin_headers)
    assert r.status_code == 200
    types = r.json()
    assert len(types) > 0
    for pt in types:
        assert pt["portal_url"].startswith("https://")
        assert pt["portal_name"]


def test_start_application_is_a_draft_not_a_submission(client, tourist_headers, db, tourist_user):
    t = db.get(Tourist, tourist_user.tourist_id)
    r = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/permits", headers=tourist_headers,
        json={"permit_type": "wildlife_sanctuary_permit", "destination_name": "Kaziranga"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "draft"
    # No reference number yet -- nothing has been reviewed/confirmed.
    assert body["reference_no"] is None
    assert body["submitted_at"] is None
    # Pre-filled from the tourist's own real profile, not invented.
    assert body["form"]["applicant_name"] == t.full_name
    assert body["form"]["nationality"] == t.nationality
    assert body["form"]["trip_start"] == t.trip_start.date().isoformat()
    assert body["form"]["purpose"] == "Tourism"


def test_confirm_never_fabricates_a_government_approval(client, tourist_headers, tourist_user):
    draft = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/permits", headers=tourist_headers,
        json={"permit_type": "forest_entry_permit", "destination_name": "Reserve Forest"},
    ).json()

    r = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/permits/{draft['id']}/confirm", headers=tourist_headers,
    )
    assert r.status_code == 200
    body = r.json()
    # Reviewed and tagged with a LOCAL tracking id, never "approved" by any
    # government authority -- the status vocabulary itself must not imply that.
    assert body["status"] == "reviewed"
    assert body["reference_no"].startswith("MUSAFIR-REF-")
    # The real official portal is handed back so the tourist finishes there.
    assert body["portal"]["portal_url"].startswith("https://")


def test_only_a_draft_can_be_edited(client, tourist_headers, tourist_user):
    draft = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/permits", headers=tourist_headers,
        json={"permit_type": "wildlife_sanctuary_permit", "destination_name": "Kaziranga"},
    ).json()
    client.post(f"/api/tourists/{tourist_user.tourist_id}/permits/{draft['id']}/confirm", headers=tourist_headers)

    r = client.patch(
        f"/api/tourists/{tourist_user.tourist_id}/permits/{draft['id']}", headers=tourist_headers,
        json={"form": {"applicant_name": "Someone Else"}},
    )
    assert r.status_code == 400


def test_a_confirmed_application_cannot_be_confirmed_twice(client, tourist_headers, tourist_user):
    draft = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/permits", headers=tourist_headers,
        json={"permit_type": "wildlife_sanctuary_permit", "destination_name": "Kaziranga"},
    ).json()
    client.post(f"/api/tourists/{tourist_user.tourist_id}/permits/{draft['id']}/confirm", headers=tourist_headers)
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/permits/{draft['id']}/confirm", headers=tourist_headers)
    assert r.status_code == 400


def test_tourist_cannot_see_another_tourists_permit(client, tourist_headers, db, admin_headers):
    other = make_tourist(db, name="Someone Else")
    r = client.post(
        f"/api/tourists/{other.id}/permits", headers=tourist_headers,
        json={"permit_type": "wildlife_sanctuary_permit", "destination_name": "Kaziranga"},
    )
    assert r.status_code == 403


def test_restricted_zone_suggests_the_right_permit_type():
    from app.services.permit import required_for_zone

    class FakeZone:
        risk_level = "restricted"

    assert required_for_zone(FakeZone()) == ["restricted_area_permit"]
    assert required_for_zone(None) == []


def test_unknown_permit_type_is_rejected(client, tourist_headers, tourist_user):
    r = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/permits", headers=tourist_headers,
        json={"permit_type": "not_a_real_permit", "destination_name": "Nowhere"},
    )
    assert r.status_code == 400
