"""
Converte as imagens catalogadas do LPF em embeddings e monta o índice FAISS.

    python -m backend.scripts.build_index --augment 8

Como funciona:
  1. lê data/dataset_lpf.json e resolve o caminho local de cada imagem
  2. gera K vistas por imagem (rotações + flips, o mesmo TTA da inferência),
     porque a maioria das espécies tem UMA única foto oficial — sem isso o
     índice teria 1 vetor por classe e nenhuma tolerância a orientação
  3. extrai embeddings em lote e grava xiloscan.faiss + metadados
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.catalog import Catalog  # noqa: E402
from backend.app.config import get_settings  # noqa: E402
from backend.app.index import VectorIndex  # noqa: E402
from backend.app.model import load_embedder, resolve_device  # noqa: E402
from backend.app.preprocessing import preprocess, to_batch, tta_variants  # noqa: E402
from backend.app.schemas import SECOES_CORTE  # noqa: E402

log = logging.getLogger("xiloscan.build_index")


def resolver_imagem(entrada: str | None, images_root: Path, data_root: Path) -> Path | None:
    if not entrada:
        return None
    p = Path(entrada)
    for cand in (p, data_root / p, images_root / p.name, data_root / "images" / p.name):
        if cand.exists() and cand.is_file():
            return cand
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--augment", type=int, default=8, choices=[1, 2, 4, 8],
                    help="vistas por imagem (8 = 4 rotações × flip)")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0, help="processar só N espécies (debug)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    s = get_settings()
    device = resolve_device(s.device)
    model, treinado = load_embedder(s.checkpoint, s.backbone, s.embedding_dim, device)
    if not treinado:
        log.warning("SEM checkpoint treinado — índice construído sobre features ImageNet. "
                    "Use apenas para desenvolvimento.")

    catalog = Catalog.load(s.dataset_path)
    especies = catalog.all()[: args.limit] if args.limit else catalog.all()
    log.info("%d espécies no catálogo", len(especies))

    vetores: list[np.ndarray] = []
    labels: list[str] = []
    caminhos: list[str] = []
    tipos: list[str] = []
    sem_imagem: list[str] = []

    buffer: list[np.ndarray] = []
    buf_labels: list[str] = []
    buf_paths: list[str] = []
    buf_tipos: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        with torch.inference_mode():
            emb = model(to_batch(buffer).to(device)).cpu().numpy()
        vetores.append(emb)
        labels.extend(buf_labels)
        caminhos.extend(buf_paths)
        tipos.extend(buf_tipos)
        buffer.clear(); buf_labels.clear(); buf_paths.clear(); buf_tipos.clear()

    for i, esp in enumerate(especies, 1):
        # indexa só as vistas do lenho (transversal/tangencial/radial); árvore,
        # tora e casca são contexto para o detalhe, não servem à comparação.
        fotos = [im for im in esp.imagens if im.tipo in SECOES_CORTE]
        if not fotos:
            sem_imagem.append(esp.id)
            continue
        for im in fotos:
            img_path = resolver_imagem(im.arquivo, s.images_root, s.dataset_path.parent)
            if img_path is None:
                continue
            try:
                chw = preprocess(str(img_path), s.image_size, s.clahe_clip_limit,
                                 s.clahe_grid, s.center_crop_ratio)
            except Exception as exc:  # noqa: BLE001
                log.error("falha ao pré-processar %s: %s", img_path, exc)
                continue
            vistas = tta_variants(chw)[: args.augment] if args.augment > 1 else [chw]
            for v in vistas:
                buffer.append(v)
                buf_labels.append(esp.id)
                buf_paths.append(str(img_path))
                buf_tipos.append(im.tipo)
                if len(buffer) >= args.batch_size:
                    flush()
        if i % 25 == 0:
            log.info("  %d/%d espécies", i, len(especies))
    flush()

    if not vetores:
        log.error("nenhum embedding gerado — rode o scraper com download de imagens primeiro")
        return 1

    matriz = np.vstack(vetores).astype(np.float32)
    log.info("embeddings: %s | espécies com imagem: %d | sem imagem: %d",
             matriz.shape, len(set(labels)), len(sem_imagem))
    if sem_imagem:
        log.warning("sem imagem local: %s%s", sem_imagem[:12],
                    " ..." if len(sem_imagem) > 12 else "")

    index = VectorIndex(s.embedding_dim, s.index_type)
    index.build(matriz, labels, caminhos, tipos)
    index.save(s.index_path, s.index_meta_path)
    log.info("✔ índice pronto: %d vetores / %d espécies", index.n_vectors, index.n_species)
    return 0


if __name__ == "__main__":
    sys.exit(main())
