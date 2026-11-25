"""Testes unitários do monitor de Fatos Relevantes da CVM (IPE)."""

from datetime import date
from unittest.mock import patch

from sqlmodel import Session

from app.database.models import Asset, AssetClass
from app.database.session import engine
from app.services.events import (
    events_report,
    parse_cvm_ipe_csv,
    parse_fnet_payload,
    sync_cvm_events,
    toggle_read,
)


def test_parse_cvm_ipe_csv_filtra_ativos_e_categorias() -> None:
    today = date.today().isoformat()
    csv_sample = (
        "CNPJ_Companhia;Nome_Companhia;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
        "Data_Entrega;Link_Download;Protocolo_Entrega\n"
        f"00.000.000/0001-91;BANCO DO BRASIL S.A.;{today};Fato Relevante;Fato Relevante;;"
        f"Revisao de guidance 2026;{today};https://cvm.gov.br/doc1.pdf;PROT-001\n"
        f"00.000.000/0001-91;BANCO DO BRASIL S.A.;{today};Calendario de Eventos;;;"
        f"Calendario anual;{today};https://cvm.gov.br/doc2.pdf;PROT-002\n"
        f"99.999.999/0001-00;EMPRESA QUALQUER S.A.;{today};Fato Relevante;Fato Relevante;;"
        f"Nao monitorada;{today};https://cvm.gov.br/doc3.pdf;PROT-003\n"
    )
    items = parse_cvm_ipe_csv(csv_sample, {"BBAS3", "EGIE3"}, days_back=30)
    assert len(items) == 1
    assert items[0].ticker == "BBAS3"
    assert items[0].protocol == "PROT-001"
    assert "guidance" in items[0].subject


def test_sync_cvm_events_deduplica_e_marca_lido() -> None:
    today = date.today().isoformat()
    csv_sample = (
        "CNPJ_Companhia;Nome_Companhia;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
        "Data_Entrega;Link_Download;Protocolo_Entrega\n"
        f"02.474.103/0001-19;ENGIE BRASIL ENERGIA S.A.;{today};Aviso aos Acionistas;;;"
        f"Distribuicao de JCP;{today};https://cvm.gov.br/jcp.pdf;PROT-100\n"
    )
    with Session(engine) as session:
        cls = AssetClass(name="Ações", target_pct=100.0)
        session.add(cls)
        session.commit()
        session.refresh(cls)
        assert cls.id is not None

        session.add(Asset(ticker="EGIE3", asset_class_id=cls.id, quantity=6, current_price=25.0))
        session.commit()

        with patch("app.services.events._download_cvm_ipe_csv", return_value=csv_sample):
            created_1, _ = sync_cvm_events(session)
            created_2, _ = sync_cvm_events(session)

        assert created_1 == 1
        assert created_2 == 0  # deduplicação por protocolo

        report = events_report(session)
        assert len(report.events) == 1
        assert report.unread_count == 1
        ev_id = report.events[0].id
        assert ev_id is not None

        toggled = toggle_read(session, ev_id)
        assert toggled is not None
        assert toggled.is_read is True
        assert events_report(session).unread_count == 0


def test_parse_fnet_payload_filtra_documentos_fii() -> None:
    payload: dict[str, object] = {
        "data": [
            {
                "id": 1390465,
                "descricaoFundo": "PATRIA LOG FII",
                "categoriaDocumento": "Relatórios",
                "tipoDocumento": "Relatório Gerencial",
                "assunto": None,
                "dataEntrega": "23/11/2026 21:31",
            },
            {
                "id": 1389612,
                "descricaoFundo": "PATRIA LOG FII",
                "categoriaDocumento": "Fato Relevante",
                "tipoDocumento": "",
                "assunto": "Aquisicao de galpao",
                "dataEntrega": "19/11/2026 19:48",
            },
            {
                "id": 1385439,
                "descricaoFundo": "PATRIA LOG FII",
                "categoriaDocumento": "Informes Periódicos",
                "tipoDocumento": "Informe Mensal Estruturado",
                "assunto": None,
                "dataEntrega": "13/11/2026 19:55",
            },
        ]
    }
    items = parse_fnet_payload("HGLG11", payload)
    assert len(items) == 2
    assert items[0].protocol == "FNET-1390465"
    assert items[0].category == "Relatório Gerencial"
    assert items[1].protocol == "FNET-1389612"
    assert "exibirDocumento?id=1389612" in items[1].document_url
