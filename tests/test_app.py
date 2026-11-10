def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_home_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SportZone" in resp.get_data(as_text=True)


def test_404_page(client):
    resp = client.get("/khong-ton-tai")
    assert resp.status_code == 404
    assert "Không tìm thấy trang" in resp.get_data(as_text=True)


def test_security_headers(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
