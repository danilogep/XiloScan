"""Testes do backend que não dependem de pesos treinados."""
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.app.catalog import Catalog
from backend.app.hybrid import HybridScorer
from backend.app.index import VectorIndex
from backend.app.preprocessing import (
    apply_clahe,
    center_crop,
    gray_world_wb,
    preprocess,
    quality_report,
    tta_variants,
)
from backend.app.schemas import AnatomicalFeatures

ROOT = Path(__file__).resolve().parents[2]
TAX = ROOT / "data" / "mcb_taxonomy.json"


def fake_wood(size=(900, 700), tint=(190, 130, 70), seed=0) -> bytes:
    """Textura sintética com 'poros' escuros — suficiente para exercitar o pipeline."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size[1], size[0], 3), np.uint8)
    img[:, :] = tint
    img = np.clip(img + rng.normal(0, 12, img.shape), 0, 255).astype(np.uint8)
    for _ in range(300):
        y, x = rng.integers(0, size[1]), rng.integers(0, size[0])
        r = int(rng.integers(3, 8))
        img[max(0, y - r):y + r, max(0, x - r):x + r] //= 3
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=92)
    return buf.getvalue()


# ───────────────────────────────────────────────────────── pré-processamento

def test_preprocess_shape_e_normalizacao():
    out = preprocess(fake_wood(), image_size=224)
    assert out.shape == (3, 224, 224)
    assert out.dtype == np.float32
    assert -4.0 < out.min() and out.max() < 4.0   # faixa ImageNet


def test_center_crop_quadrado():
    img = np.zeros((700, 900, 3), np.uint8)
    c = center_crop(img, 0.85)
    assert c.shape[0] == c.shape[1] == int(700 * 0.85)


def test_clahe_aumenta_contraste_local():
    img = np.full((256, 256, 3), 128, np.uint8)
    img[64:192, 64:192] = 140          # baixo contraste
    out = apply_clahe(img, 3.0, 8)
    assert out.std() > img.std()


def test_white_balance_neutraliza_dominante_amarela():
    quente = np.zeros((64, 64, 3), np.uint8)
    quente[:, :] = (220, 170, 60)      # luz quente
    bal = gray_world_wb(quente)
    canais = bal.reshape(-1, 3).mean(axis=0)
    assert canais.max() - canais.min() < (np.float32([220, 170, 60]).max() - 60)


def test_tta_gera_8_vistas_distintas():
    chw = preprocess(fake_wood(), image_size=64)
    vistas = tta_variants(chw)
    assert len(vistas) == 8
    assert all(v.shape == (3, 64, 64) for v in vistas)
    assert len({v.tobytes() for v in vistas}) == 8


def test_quality_report_reprova_imagem_ruim():
    escura = Image.new("RGB", (200, 200), (8, 8, 8))
    buf = io.BytesIO(); escura.save(buf, "JPEG")
    rep = quality_report(buf.getvalue())
    assert rep["aceitavel"] is False
    assert any("Resolução baixa" in a for a in rep["avisos"])
    assert any("escura" in a for a in rep["avisos"])


def test_quality_report_aprova_imagem_boa():
    rep = quality_report(fake_wood(size=(1200, 1000)))
    assert rep["largura"] == 1200
    assert rep["nitidez_laplaciana"] > 80


# ──────────────────────────────────────────────────────────── índice FAISS

def make_index(dim=32):
    rng = np.random.default_rng(7)
    base = rng.normal(size=(3, dim)).astype(np.float32)
    vecs, ids, paths = [], [], []
    for i, sid in enumerate(["esp_a", "esp_b", "esp_c"]):
        for j in range(4):                       # 4 vistas por espécie
            v = base[i] + rng.normal(0, 0.05, dim).astype(np.float32)
            vecs.append(v); ids.append(sid); paths.append(f"/img/{sid}_{j}.jpg")
    idx = VectorIndex(dim)
    idx.build(np.vstack(vecs), ids, paths)
    return idx, base


def test_index_agrega_por_especie_e_recupera_top1():
    idx, base = make_index()
    assert idx.n_vectors == 12 and idx.n_species == 3
    res = idx.search_species(base[1], top_k=3)
    assert len(res) == 3                          # 3 espécies, não 12 vetores
    assert res[0][0] == "esp_b"
    assert 0.0 <= res[0][1] <= 1.0
    assert res[0][1] > res[1][1]
    assert res[0][2].startswith("/img/esp_b")


def test_index_roundtrip_disco(tmp_path):
    idx, base = make_index()
    ip, mp = tmp_path / "i.faiss", tmp_path / "i.json"
    idx.save(ip, mp)
    carregado = VectorIndex.load(ip, mp)
    assert carregado.n_vectors == idx.n_vectors
    assert carregado.search_species(base[0], 1)[0][0] == "esp_a"


def test_index_detecta_inconsistencia(tmp_path):
    idx, _ = make_index()
    ip, mp = tmp_path / "i.faiss", tmp_path / "i.json"
    idx.save(ip, mp)
    meta = json.loads(mp.read_text()); meta["species_ids"] = meta["species_ids"][:5]
    mp.write_text(json.dumps(meta))
    with pytest.raises(RuntimeError, match="inconsistente"):
        VectorIndex.load(ip, mp)


def test_index_rejeita_dimensao_errada():
    with pytest.raises(ValueError):
        VectorIndex(32).build(np.zeros((4, 16), np.float32), ["a"] * 4, ["p"] * 4)


# ──────────────────────────────────────────────────────────── filtro híbrido

@pytest.fixture()
def scorer():
    return HybridScorer(TAX, peso_visual=0.7)


ESPECIE = AnatomicalFeatures(
    dominio_fitogeografico=["AMAZONIA"], cor_madeira="AMARELA",
    vasos_porosidade="DIFUSA", vasos_agrupamento=["SOLITARIOS", "MULTIPLOS_RADIAIS"],
    parenquima_axial="PARATRAQUEAL", parenquima_paratraqueal=["ALIFORME_CONFLUENTE"],
)


def test_atributos_iguais_dao_score_1(scorer):
    s, _ = scorer.compare_features(ESPECIE, ESPECIE)
    assert s == pytest.approx(1.0)


def test_atributo_divergente_derruba_score(scorer):
    usuario = AnatomicalFeatures(cor_madeira="MARROM_ESCURA")
    s, det = scorer.compare_features(usuario, ESPECIE)
    assert s == 0.0
    cor = next(d for d in det if d.campo == "cor_madeira")
    assert cor.status == "divergente"
    assert cor.valor_especie == ["AMARELA"]


def test_campo_nao_informado_e_neutro(scorer):
    """Informar só a cor (correta) deve dar 1.0, não 1/11."""
    usuario = AnatomicalFeatures(cor_madeira="AMARELA")
    s, det = scorer.compare_features(usuario, ESPECIE)
    assert s == pytest.approx(1.0)
    assert sum(1 for d in det if d.status == "nao_informado") == 10


def test_lacuna_no_dataset_nao_pune_usuario(scorer):
    """Espécie sem raios preenchidos: o campo sai do denominador."""
    usuario = AnatomicalFeatures(raios_visibilidade=["SOB_LENTE"], cor_madeira="AMARELA")
    s, det = scorer.compare_features(usuario, ESPECIE)
    assert s == pytest.approx(1.0)
    raios = next(d for d in det if d.campo == "raios_visibilidade")
    assert raios.status == "nao_informado"


def test_multivalorado_usa_cobertura(scorer):
    usuario = AnatomicalFeatures(vasos_agrupamento=["SOLITARIOS", "CACHOS"])
    s, _ = scorer.compare_features(usuario, ESPECIE)
    assert s == pytest.approx(0.5)   # 1 de 2 informados bate


def test_combine_sem_atributos_e_visual_puro(scorer):
    assert scorer.combine(0.9, 0.0, usuario_informou=False) == 0.9


def test_combine_pondera(scorer):
    assert scorer.combine(0.8, 0.5, usuario_informou=True) == pytest.approx(0.7 * 0.8 + 0.3 * 0.5)


def test_niveis_de_confianca(scorer):
    assert scorer.nivel(0.95).value == "alta"
    assert scorer.nivel(0.70).value == "media"
    assert scorer.nivel(0.30).value == "baixa"


def test_top1_ambiguo(scorer):
    assert scorer.top1_ambiguo([0.81, 0.79]) is True
    assert scorer.top1_ambiguo([0.91, 0.60]) is False
    assert scorer.top1_ambiguo([0.9]) is False


def test_usuario_informou(scorer):
    assert scorer.usuario_informou(AnatomicalFeatures()) is False
    assert scorer.usuario_informou(AnatomicalFeatures(cor_madeira="AMARELA")) is True


# ───────────────────────────────────────────────────────────────── catálogo

def test_catalog_carrega_dataset_de_exemplo(tmp_path):
    ds = {
        "meta": {"versao": "1"},
        "especies": [{
            "id": "alexa_grandiflora", "lpf_id": 284, "fonte_url": "http://x",
            "taxonomia": {"nome_cientifico": "Alexa grandiflora", "autor": "Ducke",
                          "familia": "Fabaceae", "sinonimos": [],
                          "nomes_populares": ["Melancieira"], "grafia_original_lpf": "Alexa grandiflora"},
            "procedencia": {"local_coleta": "Santarém-PA", "dominio_fitogeografico": ["AMAZONIA"]},
            "caracteres_gerais": {"cor_descricao": "amarelo-amarronzado", "gra": "cruzada ondulada",
                                  "textura": "média a grossa"},
            "anatomia_macroscopica": {"aneis_crescimento": "POUCO_DISTINTOS", "cor_madeira": "AMARELA",
                                      "vasos_porosidade": "DIFUSA", "vasos_agrupamento": [],
                                      "vasos_obstrucao": None, "tiloses_substancias": [],
                                      "parenquima_axial": None, "parenquima_apotraqueal": [],
                                      "parenquima_paratraqueal": [], "raios_visibilidade": []},
            "propriedades": {"Densidade (g/cm³) · Básica": 0.60},
            "propriedades_chave": {"densidade_basica": 0.60},
            "imagens": [{"url": "http://i/x.jpg", "arquivo": "images/Alexa_grandiflora/Alexa_grandiflora_01.jpg"}],
            "completeness": 0.41,
        }],
    }
    p = tmp_path / "d.json"; p.write_text(json.dumps(ds), encoding="utf-8")
    cat = Catalog.load(p)
    esp = cat.get("alexa_grandiflora")
    assert len(cat) == 1
    assert esp.taxonomia.familia == "Fabaceae"
    assert esp.densidade_basica == pytest.approx(0.60)
    assert esp.anatomia.dominio_fitogeografico == ["AMAZONIA"]   # veio de procedencia
    assert esp.imagem_url.endswith("Alexa_grandiflora_01.jpg")
    assert cat.get("inexistente") is None
