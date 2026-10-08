"""
XiloScan API — FastAPI.

Rotas:
  GET  /health
  GET  /taxonomy               vocabulário controlado para montar os filtros no frontend
  GET  /species                catálogo paginado
  GET  /species/{id}
  POST /identify               imagem (+ atributos opcionais) -> ComparisonResult
  POST /quality-check          checagem barata de foco/luz antes de identificar
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import torch
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .catalog import Catalog
from .config import Settings, get_settings
from .hybrid import HybridScorer
from .index import VectorIndex
from .model import load_embedder, resolve_device
from .preprocessing import preprocess, quality_report, to_batch, tta_variants
from .schemas import (
    ComparisonResult,
    HealthResponse,
    IdentifyOptions,
    SpeciesMatch,
)

log = logging.getLogger("xiloscan.api")
STATE: dict = {}

# Cadastro (Railway/Postgres). Opcional: no Colab, sem SQLAlchemy, a API de
# identificação roda igual — só não expõe /auth.
try:
    from .auth import init_db as _init_auth_db
    from .auth import router as _auth_router
    _AUTH_OK = True
except Exception as _exc:  # noqa: BLE001
    _AUTH_OK = False
    logging.getLogger("xiloscan.api").warning("auth desativado (%s)", _exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    device = resolve_device(s.device)

    STATE["device"] = device
    STATE["catalog"] = Catalog.load(s.dataset_path) if s.dataset_path.exists() else Catalog({}, {})
    STATE["scorer"] = HybridScorer(
        s.taxonomy_path, s.peso_visual, s.limiar_alta_confianca, s.limiar_media_confianca
    )

    try:
        model, treinado = load_embedder(s.checkpoint, s.backbone, s.embedding_dim, device)
        STATE["model"] = model
        STATE["treinado"] = treinado
        if not treinado:
            log.warning(
                "checkpoint ausente (%s) — rodando com pesos ImageNet. "
                "Acurácia de desenvolvimento apenas: treine com scripts/train.py",
                s.checkpoint,
            )
    except Exception:
        log.exception("falha ao carregar o modelo")
        STATE["model"] = None
        STATE["treinado"] = False

    try:
        STATE["index"] = VectorIndex.load(s.index_path, s.index_meta_path)
    except Exception as exc:
        log.warning("índice FAISS indisponível (%s) — rode scripts/build_index.py", exc)
        STATE["index"] = None

    if _AUTH_OK:
        try:
            _init_auth_db()
            log.info("cadastro (auth) ativo")
        except Exception:  # noqa: BLE001
            log.exception("falha ao inicializar o banco de cadastro")

    log.info("XiloScan pronto: %d espécies | device=%s", len(STATE["catalog"]), device)
    yield
    STATE.clear()


app = FastAPI(
    title="XiloScan API",
    version="1.0.0",
    description="Identificação de madeiras por imagem macroscópica — catálogo LPF/SFB + vocabulário anatômico do app Madeiras Comerciais do Brasil (MCB).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

if _AUTH_OK:
    app.include_router(_auth_router)

_img_root = get_settings().images_root
if _img_root.exists():
    app.mount("/static/images", StaticFiles(directory=str(_img_root)), name="images")


# ───────────────────────────────────────────────────────────────── endpoints

@app.get("/health", response_model=HealthResponse)
def health(s: Settings = Depends(get_settings)) -> HealthResponse:
    idx: VectorIndex | None = STATE.get("index")
    ok = STATE.get("model") is not None and idx is not None and len(STATE["catalog"]) > 0
    return HealthResponse(
        status="ok" if ok else "degradado",
        modelo_carregado=STATE.get("model") is not None,
        indice_carregado=idx is not None,
        n_especies=len(STATE.get("catalog", [])),
        n_vetores=idx.n_vectors if idx else 0,
        device=str(STATE.get("device", "?")),
        backbone=s.backbone,
    )


@app.get("/taxonomy")
def taxonomy(s: Settings = Depends(get_settings)):
    return JSONResponse(json.loads(Path(s.taxonomy_path).read_text(encoding="utf-8")))


@app.get("/species")
def list_species(offset: int = 0, limit: int = 50, q: str = ""):
    todas = STATE["catalog"].all()
    if q:
        ql = q.lower()
        todas = [
            e for e in todas
            if ql in e.taxonomia.nome_cientifico.lower()
            or any(ql in n.lower() for n in e.taxonomia.nomes_populares)
        ]
    return {"total": len(todas), "items": todas[offset : offset + limit]}


@app.get("/species/{species_id}")
def get_species(species_id: str):
    esp = STATE["catalog"].get(species_id)
    if esp is None:
        raise HTTPException(404, f"espécie '{species_id}' não encontrada")
    return esp


def _ref_url(img_ref: str | None, images_root) -> str | None:
    """caminho absoluto do vetor indexado -> URL servível /static/images/<sub>/<arq>."""
    if not img_ref:
        return None
    try:
        rel = Path(img_ref).resolve().relative_to(Path(images_root).resolve())
        return f"/static/images/{rel.as_posix()}"
    except Exception:  # noqa: BLE001
        return None


async def _read_upload(file: UploadFile, max_mb: int) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "arquivo vazio")
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"arquivo acima de {max_mb} MB")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(415, f"tipo não suportado: {file.content_type}")
    return data


@app.post("/quality-check")
async def quality_check(file: UploadFile = File(...), s: Settings = Depends(get_settings)):
    data = await _read_upload(file, s.max_upload_mb)
    try:
        return quality_report(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"não foi possível ler a imagem: {exc}") from exc


@app.post("/identify", response_model=ComparisonResult)
async def identify(
    file: UploadFile = File(...),
    options: str = Form("{}"),
    s: Settings = Depends(get_settings),
):
    t0 = time.perf_counter()
    model = STATE.get("model")
    idx: VectorIndex | None = STATE.get("index")
    if model is None or idx is None:
        raise HTTPException(503, "modelo ou índice indisponível — veja /health")

    try:
        opts = IdentifyOptions.model_validate_json(options or "{}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"campo 'options' inválido: {exc}") from exc

    data = await _read_upload(file, s.max_upload_mb)

    # 1. pré-processamento + TTA
    try:
        chw = preprocess(
            data, s.image_size, s.clahe_clip_limit, s.clahe_grid, s.center_crop_ratio
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"imagem ilegível: {exc}") from exc

    variantes = tta_variants(chw) if s.tta_enabled else [chw]
    batch = to_batch(variantes)

    # 2. embedding (média L2-normalizada das vistas)
    with torch.inference_mode():
        embs = model(batch.to(STATE["device"])).cpu().numpy()
    query = embs.mean(axis=0)
    query /= np.linalg.norm(query) + 1e-12

    # 3. busca vetorial (restrita à seção escolhida, se houver)
    secoes = {opts.secao} if opts.secao else None
    brutos = idx.search_species(query, top_k=max(opts.top_k * 2, 20), secoes=secoes)

    # 4. filtro híbrido
    scorer: HybridScorer = STATE["scorer"]
    informou = scorer.usuario_informou(opts.atributos)
    catalog: Catalog = STATE["catalog"]

    matches: list[SpeciesMatch] = []
    for species_id, score_visual, img_ref in brutos:
        esp = catalog.get(species_id)
        if esp is None:
            continue
        score_attr, detalhes = scorer.compare_features(opts.atributos, esp.anatomia)
        final = scorer.combine(score_visual, score_attr, informou, opts.peso_visual)
        matches.append(SpeciesMatch(
            especie=esp,
            score_visual=round(score_visual, 4),
            score_atributos=round(score_attr, 4),
            score_final=round(final, 4),
            confianca_pct=round(final * 100, 1),
            nivel=scorer.nivel(final),
            features=detalhes,
            imagem_referencia_url=_ref_url(img_ref, s.images_root) or esp.imagem_url,
        ))

    matches.sort(key=lambda m: m.score_final, reverse=True)
    matches = matches[: opts.top_k]

    return ComparisonResult(
        request_id=str(uuid.uuid4()),
        imagem_usuario_url="",  # preenchido pelo cliente (objectURL) ou por storage
        processado_em_ms=int((time.perf_counter() - t0) * 1000),
        secao_consultada=opts.secao,
        matches=matches,
        top1_ambiguo=scorer.top1_ambiguo([m.score_final for m in matches]),
    )


# ── SPA (deploy único no Railway): serve o frontend construído na mesma origem.
# Montado por ÚLTIMO, para não capturar as rotas da API. Guardado pela existência
# do dist — no Colab (identify-only) nada muda.
_frontend_dist = Path(
    os.getenv("XILOSCAN_FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist"))
)
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="spa")
    log.info("SPA servido de %s", _frontend_dist)
