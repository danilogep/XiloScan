"""
Integração ponta-a-ponta: dataset sintético -> índice FAISS -> API /identify.

Usa resnet18 + checkpoint aleatório salvo em disco (evita download de pesos)
e imagens sintéticas com texturas distintas por 'espécie'. O objetivo não é
medir acurácia — é provar que o contrato inteiro fecha: upload multipart,
pré-processamento, TTA, busca vetorial, filtro híbrido e serialização.
"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]

ESPECIES = [
    ("alexa_grandiflora", "Alexa grandiflora", "Alexa_grandiflora", (200, 150, 80), "AMARELA", "DIFUSA"),
    ("acioa_edulis", "Acioa edulis", "Acioa_edulis", (120, 70, 55), "MARROM_ESCURA", "ANEL_POROSO"),
    ("aniba_canelilla", "Aniba canelilla", "Aniba_canelilla", (215, 195, 150), "BRANCA_BEGE", "DIFUSA"),
]


def textura(tint, seed, n_poros, raio, size=760):
    rng = np.random.default_rng(seed)
    img = np.full((size, size, 3), tint, np.uint8)
    img = np.clip(img + rng.normal(0, 10, img.shape), 0, 255).astype(np.uint8)
    for _ in range(n_poros):
        y, x = rng.integers(raio, size - raio, 2)
        img[y - raio:y + raio, x - raio:x + raio] //= 3
    return Image.fromarray(img)


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    base = tmp_path_factory.mktemp("xiloscan_e2e")
    data, art = base / "data", base / "artifacts"
    (data / "images").mkdir(parents=True); art.mkdir()

    especies_json = []
    for i, (sid, nome, folder, tint, cor, poros) in enumerate(ESPECIES):
        d = data / "images" / folder
        d.mkdir()
        for j in range(3):
            textura(tint, seed=i * 10 + j, n_poros=60 + i * 220, raio=3 + i * 3).save(
                d / f"{folder}_{j:02d}.jpg", quality=93
            )
        especies_json.append({
            "id": sid, "lpf_id": 100 + i, "fonte_url": f"http://lpf/{i}",
            "taxonomia": {"nome_cientifico": nome, "autor": "", "familia": "Fabaceae",
                          "sinonimos": [], "nomes_populares": [nome.split()[0]]},
            "procedencia": {"local_coleta": "", "dominio_fitogeografico": ["AMAZONIA"]},
            "caracteres_gerais": {"cor_descricao": "", "gra": "", "textura": ""},
            "anatomia_macroscopica": {
                "aneis_crescimento": "DISTINTOS", "cor_madeira": cor,
                "vasos_porosidade": poros, "vasos_agrupamento": ["SOLITARIOS"],
                "vasos_obstrucao": None, "tiloses_substancias": [],
                "parenquima_axial": "PARATRAQUEAL", "parenquima_apotraqueal": [],
                "parenquima_paratraqueal": ["VASICENTRICO"], "raios_visibilidade": [],
            },
            "propriedades": {}, "imagens": [
                {"url": "", "arquivo": f"images/{folder}/{folder}_00.jpg"}
            ],
            "completeness": 0.7,
        })

    (data / "dataset_lpf.json").write_text(
        json.dumps({"meta": {}, "especies": especies_json}, ensure_ascii=False), encoding="utf-8"
    )

    # checkpoint aleatório: evita baixar pesos ImageNet e mantém o teste offline
    sys.path.insert(0, str(ROOT))
    from backend.app.model import XiloEmbedder
    emb = XiloEmbedder("resnet18", embedding_dim=64, pretrained=False)
    torch.save({"embedder": emb.state_dict()}, art / "ck.pt")

    env = {
        **os.environ,
        "XILOSCAN_DATASET_PATH": str(data / "dataset_lpf.json"),
        "XILOSCAN_TAXONOMY_PATH": str(ROOT / "data" / "mcb_taxonomy.json"),
        "XILOSCAN_IMAGES_ROOT": str(data / "images"),
        "XILOSCAN_ARTIFACTS_DIR": str(art),
        "XILOSCAN_BACKBONE": "resnet18",
        "XILOSCAN_EMBEDDING_DIM": "64",
        "XILOSCAN_IMAGE_SIZE": "128",
        "XILOSCAN_CHECKPOINT": str(art / "ck.pt"),
        "XILOSCAN_INDEX_PATH": str(art / "x.faiss"),
        "XILOSCAN_INDEX_META_PATH": str(art / "x.json"),
        "XILOSCAN_DEVICE": "cpu",
        "PYTHONPATH": str(ROOT),
    }
    r = subprocess.run(
        [sys.executable, "-m", "backend.scripts.build_index", "--augment", "4", "--batch-size", "8"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return env, data


@pytest.fixture(scope="module")
def client(ambiente):
    env, _ = ambiente
    os.environ.update({k: v for k, v in env.items() if k.startswith("XILOSCAN_")})
    from backend.app.config import get_settings
    get_settings.cache_clear()
    import importlib

    from backend.app import main as main_mod
    importlib.reload(main_mod)
    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        yield c


def test_build_index_gerou_vetores(ambiente):
    env, _ = ambiente
    meta = json.loads(Path(env["XILOSCAN_INDEX_META_PATH"]).read_text())
    assert meta["n_vectors"] == 3 * 4          # 3 espécies × 4 vistas (1 imagem cada)
    assert set(meta["species_ids"]) == {s[0] for s in ESPECIES}


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "ok"
    assert b["modelo_carregado"] and b["indice_carregado"]
    assert b["n_especies"] == 3 and b["n_vetores"] == 12


def test_taxonomy_expoe_11_categorias(client):
    b = client.get("/taxonomy").json()
    assert len(b["categorias"]) == 11
    assert {c["chave"] for c in b["categorias"]} >= {"vasos_porosidade", "raios_visibilidade"}


def test_species_listagem_e_busca(client):
    assert client.get("/species").json()["total"] == 3
    r = client.get("/species", params={"q": "acioa"}).json()
    assert r["total"] == 1 and r["items"][0]["id"] == "acioa_edulis"
    assert client.get("/species/acioa_edulis").status_code == 200
    assert client.get("/species/nao_existe").status_code == 404


def upload(nome="q.jpg", img=None):
    buf = io.BytesIO()
    (img or textura((200, 150, 80), 999, 60, 3)).save(buf, "JPEG", quality=93)
    buf.seek(0)
    return {"file": (nome, buf, "image/jpeg")}


def test_identify_contrato_completo(client):
    r = client.post("/identify", files=upload(), data={"options": json.dumps({"top_k": 3})})
    assert r.status_code == 200, r.text
    b = r.json()
    assert len(b["matches"]) == 3
    assert b["processado_em_ms"] >= 0
    assert "confirmação por profissional habilitado" in b["aviso"]
    m = b["matches"][0]
    assert 0.0 <= m["score_visual"] <= 1.0
    assert m["confianca_pct"] == pytest.approx(m["score_final"] * 100, abs=0.05)
    assert m["nivel"] in {"alta", "media", "baixa"}
    assert m["especie"]["taxonomia"]["nome_cientifico"]
    # ordenação decrescente
    scores = [x["score_final"] for x in b["matches"]]
    assert scores == sorted(scores, reverse=True)


def test_identify_sem_atributos_score_final_igual_ao_visual(client):
    b = client.post("/identify", files=upload(), data={"options": "{}"}).json()
    for m in b["matches"]:
        assert m["score_final"] == pytest.approx(m["score_visual"], abs=1e-3)


def test_atributos_reordenam_o_ranking(client):
    """O mesmo upload, com atributos que só a acioa satisfaz, deve promovê-la."""
    puro = client.post("/identify", files=upload(), data={"options": "{}"}).json()
    pos_sem = [m["especie"]["id"] for m in puro["matches"]].index("acioa_edulis")

    opts = {"top_k": 3, "peso_visual": 0.3,
            "atributos": {"cor_madeira": "MARROM_ESCURA", "vasos_porosidade": "ANEL_POROSO"}}
    com = client.post("/identify", files=upload(), data={"options": json.dumps(opts)}).json()
    pos_com = [m["especie"]["id"] for m in com["matches"]].index("acioa_edulis")
    assert pos_com <= pos_sem

    acioa = next(m for m in com["matches"] if m["especie"]["id"] == "acioa_edulis")
    assert acioa["score_atributos"] == pytest.approx(1.0)
    coincidentes = [f for f in acioa["features"] if f["status"] == "coincidente"]
    assert {f["campo"] for f in coincidentes} == {"cor_madeira", "vasos_porosidade"}


def test_features_trazem_divergencias_legiveis(client):
    opts = {"atributos": {"cor_madeira": "MARROM_ESCURA"}}
    b = client.post("/identify", files=upload(), data={"options": json.dumps(opts)}).json()
    alexa = next(m for m in b["matches"] if m["especie"]["id"] == "alexa_grandiflora")
    cor = next(f for f in alexa["features"] if f["campo"] == "cor_madeira")
    assert cor["status"] == "divergente"
    assert cor["rotulo"] == "Cor da Madeira"
    assert cor["valor_especie"] == ["AMARELA"]


def test_quality_check(client):
    b = client.post("/quality-check", files=upload()).json()
    assert b["largura"] == 760 and "aceitavel" in b

    ruim = io.BytesIO()
    Image.new("RGB", (120, 120), (5, 5, 5)).save(ruim, "JPEG")
    ruim.seek(0)
    b2 = client.post("/quality-check", files={"file": ("r.jpg", ruim, "image/jpeg")}).json()
    assert b2["aceitavel"] is False and b2["avisos"]


def test_rejeita_arquivo_nao_imagem(client):
    r = client.post("/identify", files={"file": ("a.txt", io.BytesIO(b"nao sou imagem"), "text/plain")})
    assert r.status_code == 415


def test_rejeita_options_malformado(client):
    r = client.post("/identify", files=upload(), data={"options": "{nao json"})
    assert r.status_code == 422
