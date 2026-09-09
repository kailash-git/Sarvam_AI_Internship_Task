from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_reset():
    assert client.get("/api/health").status_code == 200
    r = client.post("/api/reset", json={"seed": True})
    assert r.status_code == 200
    assert r.json()["seeded"] is True


def test_teach_then_format_flow():
    client.post("/api/reset", json={"seed": False})
    client.post("/api/observations/dictionary", json={
        "canonical": "Kivi", "category": "product", "aliases": ["kiwi"],
    })
    r = client.post("/api/format", json={
        "asr_text": "deploy kiwi", "formatted_text": "Deploy Kiwi.",
    })
    body = r.json()
    assert body["memory_aware_text"] == "Deploy Kivi."
    assert body["intervened"] is True
    assert body["trace"]["applied"][0]["reason_tag"] == "applied"


def test_memory_inspection_and_delete():
    client.post("/api/reset", json={"seed": True})
    entries = client.get("/api/memory").json()["entries"]
    assert len(entries) > 0
    eid = entries[0]["id"]
    assert client.get(f"/api/memory/{eid}").json()["id"] == eid
    assert client.delete(f"/api/memory/{eid}").status_code == 200
    assert client.get(f"/api/memory/{eid}").status_code == 404
