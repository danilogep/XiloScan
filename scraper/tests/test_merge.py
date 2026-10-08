"""Teste ponta-a-ponta: fixtures -> dataset -> merge MCB."""
import json
from pathlib import Path

import pytest

from scraper.lpf_scraper import parse_detail, record_to_dataset_entry
from scraper.mcb_merge import completeness, load_taxonomy, make_stub, merge

FX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = ROOT / "data" / "mcb_taxonomy.json"


@pytest.fixture()
def dataset():
    recs = [
        parse_detail((FX / "real_detalhe_284_alexa_grandiflora.html").read_text(encoding="utf-8", errors="replace"), 284, "u1"),
        parse_detail((FX / "real_detalhe_002_acioa_edulis.html").read_text(encoding="utf-8", errors="replace"), 2, "u2"),
    ]
    return {"meta": {}, "especies": [record_to_dataset_entry(r) for r in recs], "falhas": []}


@pytest.fixture()
def taxonomy():
    return load_taxonomy(TAXONOMY)


def test_taxonomia_carrega_11_categorias(taxonomy):
    assert len(taxonomy) == 11
    assert "ALIFORME_CONFLUENTE" in taxonomy["parenquima_paratraqueal"]


def test_merge_preenche_campos_mcb(dataset, taxonomy):
    overlay = {"especies": {"alexa_grandiflora": {
        "dominio_fitogeografico": ["AMAZONIA"],
        "vasos_porosidade": "DIFUSA",
        "vasos_agrupamento": ["SOLITARIOS", "MULTIPLOS_RADIAIS"],
        "vasos_obstrucao": "OBSTRUIDOS_TILOS",
        "tiloses_substancias": ["TILOS"],
        "parenquima_axial": "PARATRAQUEAL",
        "parenquima_paratraqueal": ["ALIFORME_CONFLUENTE"],
        "raios_visibilidade": ["SOB_LENTE"],
        "cor_madeira": "AMARELA",
        "aneis_crescimento": "POUCO_DISTINTOS",
    }}}
    out = merge(dataset, overlay, taxonomy)
    alexa = next(e for e in out["especies"] if e["id"] == "alexa_grandiflora")
    assert alexa["procedencia"]["dominio_fitogeografico"] == ["AMAZONIA"]
    assert alexa["anatomia_macroscopica"]["parenquima_paratraqueal"] == ["ALIFORME_CONFLUENTE"]
    assert alexa["proveniencia"]["mcb"] is True
    assert alexa["completeness"] == pytest.approx(0.94)  # 1.0 - 0.06 (parenquima_apotraqueal vazio)
    acioa = next(e for e in out["especies"] if e["id"] == "acioa_edulis")
    assert acioa["proveniencia"]["mcb"] is False
    assert acioa["completeness"] < alexa["completeness"]


def test_merge_registra_conflito_lpf_vs_mcb(dataset, taxonomy):
    # LPF diz POUCO_DISTINTOS para Alexa; MCB diz DISTINTOS
    overlay = {"especies": {"alexa_grandiflora": {"aneis_crescimento": "DISTINTOS"}}}
    out = merge(dataset, overlay, taxonomy)
    conf = out["meta"]["mcb"]["conflitos"]
    assert conf == [{"id": "alexa_grandiflora", "campo": "aneis_crescimento",
                     "lpf": "POUCO_DISTINTOS", "mcb": "DISTINTOS"}]
    alexa = next(e for e in out["especies"] if e["id"] == "alexa_grandiflora")
    assert alexa["anatomia_macroscopica"]["aneis_crescimento"] == "DISTINTOS"
    assert alexa["anatomia_macroscopica"]["aneis_crescimento_lpf"] == "POUCO_DISTINTOS"


def test_codigo_invalido_aborta(dataset, taxonomy):
    overlay = {"especies": {"alexa_grandiflora": {"vasos_porosidade": "POROSIDADE_MAGICA"}}}
    with pytest.raises(SystemExit):
        merge(dataset, overlay, taxonomy)


def test_slug_desconhecido_e_reportado_nao_explode(dataset, taxonomy):
    overlay = {"especies": {"especie_inexistente": {"cor_madeira": "AMARELA"}}}
    out = merge(dataset, overlay, taxonomy)
    assert out["meta"]["mcb"]["slugs_nao_encontrados"] == ["especie_inexistente"]


def test_stub_cobre_todas_as_especies(dataset):
    stub = make_stub(dataset)
    assert set(stub["especies"]) == {"alexa_grandiflora", "acioa_edulis"}
    assert stub["especies"]["acioa_edulis"]["nome_cientifico_mcb"] == "Acioa edulis"


def test_completeness_zero_e_um():
    assert completeness({}) == 0.0
    cheio = {"dominio_fitogeografico": ["A"], "cor_madeira": "A", "aneis_crescimento": "A",
             "vasos_porosidade": "A", "vasos_agrupamento": ["A"], "vasos_obstrucao": "A",
             "tiloses_substancias": ["A"], "parenquima_axial": "A",
             "parenquima_apotraqueal": ["A"], "parenquima_paratraqueal": ["A"],
             "raios_visibilidade": ["A"]}
    assert completeness(cheio) == pytest.approx(1.0)


def test_overlay_semeado_valida_contra_taxonomia(taxonomy):
    overlay = json.loads((ROOT / "data" / "mcb_overlay.json").read_text(encoding="utf-8"))
    assert len(overlay["especies"]) == 7
    for slug, dados in overlay["especies"].items():
        for campo, validos in taxonomy.items():
            v = dados.get(campo)
            itens = v if isinstance(v, list) else ([v] if v else [])
            assert all(i in validos for i in itens), f"{slug}.{campo}"
