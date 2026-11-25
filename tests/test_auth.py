"""Testes de autenticação Google OAuth (allowlist exclusiva) e registro de aporte."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import auth
from app.database.models import Asset, AssetClass
from app.database.session import engine
from app.main import app


def test_session_token_valida_apenas_email_autorizado() -> None:
    allowed = auth.SessionUser(email="thalesdiniz30@gmail.com", name="Thales")
    token = auth.create_session_token(allowed)
    parsed = auth.verify_session_token(token)
    assert parsed is not None
    assert parsed.email == "thalesdiniz30@gmail.com"

    # E-mail não autorizado nunca passa, mesmo com assinatura válida
    intruder = auth.SessionUser(email="outro@gmail.com", name="Intruso")
    intruder_token = auth.create_session_token(intruder)
    assert auth.verify_session_token(intruder_token) is None

    # Token adulterado falha
    assert auth.verify_session_token(token + "x") is None


def test_middleware_bloqueia_rotas_quando_auth_ativa() -> None:
    with (
        patch("app.core.config.is_auth_enabled", return_value=True),
        TestClient(app, follow_redirects=False) as client,
    ):
        # Rota privada redireciona para /login
        r = client.get("/")
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

        # Requisição HTMX recebe 401 + HX-Redirect
        r_htmx = client.post(
            "/aporte/simular", data={"valor": "400"}, headers={"HX-Request": "true"}
        )
        assert r_htmx.status_code == 401
        assert r_htmx.headers["HX-Redirect"] == "/login"

        # /login permanece acessível
        assert client.get("/login").status_code == 200

        # Com cookie assinado do e-mail autorizado, libera acesso
        token = auth.create_session_token(
            auth.SessionUser(email="thalesdiniz30@gmail.com", name="Thales")
        )
        client.cookies.set(auth.SESSION_COOKIE_NAME, token)
        assert client.get("/").status_code == 200


def test_callback_google_rejeita_csrf_e_email_nao_autorizado() -> None:
    with TestClient(app, follow_redirects=False) as client:
        # State inválido/ausente -> estado_invalido
        r = client.get("/auth/google/callback?code=abc&state=wrong")
        assert r.status_code == 303
        assert "estado_invalido" in r.headers["location"]

        # State válido, mas Google devolve usuário não autorizado -> acesso_negado
        client.cookies.set(auth.OAUTH_STATE_COOKIE, "valid-state")
        with patch("app.core.auth.exchange_google_code", return_value=None):
            r2 = client.get("/auth/google/callback?code=abc&state=valid-state")
        assert r2.status_code == 303
        assert "acesso_negado" in r2.headers["location"]


def test_aplicar_plano_atualiza_quantidade_e_preco_medio() -> None:
    with Session(engine) as session:
        cls = AssetClass(name="Ações", target_pct=100.0, band_pp=5.0)
        session.add(cls)
        session.commit()
        session.refresh(cls)
        assert cls.id is not None

        asset = Asset(
            ticker="BBSE3",
            asset_class_id=cls.id,
            quantity=2,
            avg_price=30.0,
            current_price=40.0,
            weight=1.0,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        asset_id = asset.id

    with TestClient(app) as client:
        resp = client.post("/aporte/aplicar", data={"valor": "80"})
        assert resp.status_code == 200
        assert resp.headers.get("HX-Refresh") == "true"

    with Session(engine) as session:
        updated = session.get(Asset, asset_id)
        assert updated is not None
        assert updated.quantity == 4.0  # 2 + 2 cotas a R$ 40
        assert updated.avg_price == 35.0  # (2*30 + 2*40) / 4
