"""Testes de integração das rotas web e importação CSV."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "carteira_exemplo.csv"


def test_rotas_principais_respondem_200() -> None:
    with TestClient(app) as client:
        for url in (
            "/",
            "/estatisticas",
            "/risco",
            "/valuation",
            "/screener",
            "/eventos",
            "/aporte",
            "/metas",
            "/importar",
        ):
            response = client.get(url)
            assert response.status_code == 200


def test_importar_e_simular_aporte() -> None:
    with TestClient(app) as client:
        content = SAMPLE_CSV.read_bytes()
        upload = client.post(
            "/importar",
            files={"arquivo": ("carteira_exemplo.csv", content, "text/csv")},
        )
        assert upload.status_code == 200
        assert "7 ativos importados/atualizados." in upload.text

        stats = client.get("/estatisticas")
        assert "TAEE11" in stats.text
        assert "IVVB11" in stats.text

        sim = client.post("/aporte/simular", data={"valor": "400"})
        assert sim.status_code == 200
        assert "R$ 400,00" in sim.text
