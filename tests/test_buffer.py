import os
import tempfile

import pytest

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="social-cockpit-buffer-tests-"))
import app


@pytest.mark.parametrize("statuses", [(200,), (502,), (502, 200, 400), (200, 200)])
def test_bulk_send_reports_each_actual_result(monkeypatch, statuses):
    monkeypatch.setattr(app, "rows", lambda *args: [{"id": str(i)} for i in range(len(statuses))])

    def approve(ident):
        status = statuses[int(ident)]
        response = app.jsonify(ok=True) if status == 200 else app.jsonify(error="Image unavailable " + ident)
        return response if status == 200 else (response, status)

    monkeypatch.setattr(app, "approve", approve)
    response = app.app.test_client().post("/api/drafts/send-ready")
    assert response.json == {
        "sent": statuses.count(200),
        "failed": [{"id": str(i), "error": "Image unavailable " + str(i)} for i, status in enumerate(statuses) if status >= 400],
    }


def test_image_error_identifies_urls_and_preserves_draft(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB", tmp_path / "test.db")
    app.init()
    with app.db() as connection:
        connection.execute("UPDATE settings SET buffer_token='test-token', facebook_channel='fb'")
        connection.execute("INSERT INTO drafts(id,caption,scheduled_at,status,created_at,platforms,media_id) VALUES('draft','Test','2026-10-01','ready','2026-09-15','[\"facebook\"]','library')")
    image_url = "https://images.example.com/photo.jpg"
    monkeypatch.setattr(app, "media_for", lambda *args: [{"kind": "url", "value": image_url}])
    calls = []

    def buffer_call(token, query, variables):
        calls.append(variables)
        return {"createPost": {"message": "Invalid post: Image could not be read from its URL."}}

    monkeypatch.setattr(app, "buffer_call", buffer_call)
    response = app.app.test_client().post("/api/drafts/draft/approve")
    assert response.status_code == 502
    assert image_url in response.json["error"]
    assert "private browser window" in response.json["error"]
    assert calls[0]["assets"] == [{"image": {"url": image_url}}]
    assert app.rows("SELECT status,buffer_id FROM drafts")[0] == {"status": "ready", "buffer_id": None}
