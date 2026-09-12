"""Itinerary document upload/list/edit/confirm API (app/api/itinerary.py)."""
import io
import json

from tests.conftest import make_tourist


def _upload(client, headers, tourist_id, filename="trip.txt", content=b"Delhi -> Agra -> Jaipur",
           content_type="text/plain"):
    return client.post(
        f"/api/tourists/{tourist_id}/itinerary-documents",
        files={"file": (filename, io.BytesIO(content), content_type)},
        headers=headers,
    )


def test_upload_extracts_destinations(client, tourist_headers, tourist_user):
    r = _upload(client, tourist_headers, tourist_user.tourist_id)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "extracted"
    assert [d["name"] for d in body["extracted"]["destinations"]] == ["Delhi", "Agra", "Jaipur"]
    assert body["confirmed"] is False


def test_upload_allows_files_over_the_global_1mb_body_cap(client, tourist_headers, tourist_user):
    # Regression: the itinerary upload has its own, larger, documented size
    # limit (ITINERARY_DOCUMENT_MAX_BYTES, 5 MB) -- the global per-request
    # 1 MB body-size guard (app/core/middleware.py) must not shadow it and
    # reject an itinerary file that's under 5 MB but over 1 MB.
    big_content = b"Delhi -> Agra -> Jaipur\n" + b"x" * 1_200_000
    r = _upload(client, tourist_headers, tourist_user.tourist_id, content=big_content)
    assert r.status_code == 201
    assert r.json()["status"] == "extracted"


def test_upload_forbidden_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Someone Else")
    r = _upload(client, tourist_headers, other.id)
    assert r.status_code == 403


def test_upload_unsupported_type_creates_failed_document_not_an_error(client, tourist_headers, tourist_user):
    r = _upload(client, tourist_headers, tourist_user.tourist_id,
               filename="trip.xyz", content=b"not a real document", content_type="application/x-unknown")
    assert r.status_code == 201  # graceful -- not a 4xx/5xx dead end
    body = r.json()
    assert body["status"] == "failed"
    assert "Unsupported" in body["error"]


def _jpg_bytes(text: str) -> bytes:
    import io as _io

    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (700, 150), "white")
    ImageDraw.Draw(img).text((10, 10), text, fill="black", font=ImageFont.load_default(size=40))
    buf = _io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_upload_jpg_photo_is_ocr_extracted(client, tourist_headers, tourist_user):
    # A photographed/scanned itinerary (jpg) goes through the same real
    # extract -> parse -> review pipeline as PDF/DOCX, via local OCR.
    r = _upload(client, tourist_headers, tourist_user.tourist_id,
               filename="scan.jpg", content=_jpg_bytes("Delhi -> Agra"), content_type="image/jpeg")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "extracted"
    assert [d["name"] for d in body["extracted"]["destinations"]] == ["Delhi", "Agra"]


def test_list_and_get_documents(client, tourist_headers, tourist_user):
    _upload(client, tourist_headers, tourist_user.tourist_id)
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/itinerary-documents", headers=tourist_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    doc_id = r.json()[0]["id"]

    r2 = client.get(f"/api/tourists/{tourist_user.tourist_id}/itinerary-documents/{doc_id}",
                    headers=tourist_headers)
    assert r2.status_code == 200
    assert r2.json()["id"] == doc_id


def test_edit_extracted_itinerary(client, tourist_headers, tourist_user):
    doc = _upload(client, tourist_headers, tourist_user.tourist_id).json()
    payload = doc["extracted"]
    payload["destinations"].append({"name": "Udaipur", "lat": 24.5854, "lng": 73.7125})

    r = client.patch(
        f"/api/tourists/{tourist_user.tourist_id}/itinerary-documents/{doc['id']}",
        json=payload, headers=tourist_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["extracted"]["destinations"]) == 4


def test_confirm_writes_into_tourist_itinerary(client, tourist_headers, tourist_user, db):
    doc = _upload(client, tourist_headers, tourist_user.tourist_id).json()
    r = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/itinerary-documents/{doc['id']}/confirm",
        headers=tourist_headers,
    )
    assert r.status_code == 200
    assert r.json()["confirmed"] is True

    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    saved = json.loads(t.itinerary)
    assert [w["name"] for w in saved] == ["Delhi", "Agra", "Jaipur"]


def test_confirm_skips_destinations_without_coordinates(client, tourist_headers, tourist_user, db):
    doc = _upload(client, tourist_headers, tourist_user.tourist_id,
                 content=b"Delhi -> Nowhereville -> Agra").json()
    # "Nowhereville" won't resolve via the gazetteer -- confirm should still
    # succeed, just skip that one destination rather than fabricate coords.
    r = client.post(
        f"/api/tourists/{tourist_user.tourist_id}/itinerary-documents/{doc['id']}/confirm",
        headers=tourist_headers,
    )
    assert r.status_code == 200
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    saved = json.loads(t.itinerary)
    assert "Nowhereville" not in [w["name"] for w in saved]
    assert "Delhi" in [w["name"] for w in saved]
