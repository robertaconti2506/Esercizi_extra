"""Test della probe di liveness /healthz."""


def test_healthz_risponde_200(client):
    risposta = client.get("/healthz")
    assert risposta.status_code == 200


def test_healthz_restituisce_status_ok(client):
    risposta = client.get("/healthz")
    assert risposta.json() == {"status": "ok"}


def test_healthz_non_richiede_login(client):
    # OpenShift chiama la probe senza cookie: non deve essere rediretta al login
    risposta = client.get("/healthz", follow_redirects=False)
    assert risposta.status_code == 200
    assert "location" not in risposta.headers