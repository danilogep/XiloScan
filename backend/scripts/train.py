"""
Treino do extrator com ArcFace (metric learning).

    python -m backend.scripts.train --epochs 40 --batch-size 24

Pré-requisito: mais de uma imagem por espécie. Com a foto única do LPF por
espécie, o treino aprende só invariância a augmentation — útil, mas o ganho
real vem de adicionar fotos de campo por espécie em data/images/<Especie>/.

Estratégia:
  * split estratificado por espécie (train/val), val = 1 imagem/classe quando houver
  * augmentation forte de COR e ILUMINAÇÃO (é o que varia em campo) e
    geométrica leve — sem distorcer a escala anatômica dos poros
  * warmup + cosine schedule; margem ArcFace com ramp-up (0.1 -> 0.3)
    para o modelo não colapsar nas primeiras épocas
  * métrica de validação: recall@1 por busca de cosseno contra o resto do
    conjunto (o que a aplicação de fato faz), não acurácia de softmax
"""
from __future__ import annotations

import argparse
import logging
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.config import get_settings  # noqa: E402
from backend.app.model import XiloArcFaceModel, resolve_device  # noqa: E402
from backend.app.preprocessing import preprocess  # noqa: E402

log = logging.getLogger("xiloscan.train")


class WoodDataset(Dataset):
    def __init__(self, samples: list[tuple[Path, int]], image_size: int, train: bool):
        self.samples = samples
        self.image_size = image_size
        self.train = train

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, i: int):
        path, label = self.samples[i]
        arr = preprocess(str(path), self.image_size)
        x = torch.from_numpy(arr).float()
        if self.train:
            k = random.randint(0, 3)
            if k:
                x = torch.rot90(x, k, dims=(1, 2))
            if random.random() < 0.5:
                x = torch.flip(x, dims=(2,))
            # jitter de brilho/contraste no espaço já normalizado
            x = x * random.uniform(0.88, 1.12) + random.uniform(-0.10, 0.10)
            if random.random() < 0.25:  # ruído sensor
                x = x + torch.randn_like(x) * 0.02
        return x, label


def coletar(images_root: Path) -> tuple[list[tuple[Path, int]], list[str]]:
    classes = sorted(p.name for p in images_root.iterdir() if p.is_dir())
    idx = {c: i for i, c in enumerate(classes)}
    amostras: list[tuple[Path, int]] = []
    for c in classes:
        for img in sorted((images_root / c).glob("*")):
            if img.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                amostras.append((img, idx[c]))
    return amostras, classes


def split(amostras, val_por_classe: int = 1):
    por_classe = defaultdict(list)
    for s in amostras:
        por_classe[s[1]].append(s)
    treino, val = [], []
    for _, itens in por_classe.items():
        random.shuffle(itens)
        if len(itens) > val_por_classe + 1:
            val += itens[:val_por_classe]
            treino += itens[val_por_classe:]
        else:
            treino += itens
    return treino, val


@torch.inference_mode()
def _embed(model, loader, device):
    model.eval()
    embs, labels = [], []
    for x, y in loader:
        embs.append(model.embedder(x.to(device)).cpu())
        labels.append(y)
    if not embs:
        return None, None
    return F.normalize(torch.cat(embs), dim=1), torch.cat(labels)


@torch.inference_mode()
def recall_at_1(model, query_loader, gallery_loader, device) -> float:
    """
    Recall@1 = para cada imagem de validação, a espécie do vizinho mais próximo
    na GALERIA DE TREINO é a correta? É exatamente o que o app faz (consulta
    contra o catálogo indexado). Comparar val-contra-val daria 0, pois cada
    espécie aparece uma única vez na validação.
    """
    Eq, yq = _embed(model, query_loader, device)
    Eg, yg = _embed(model, gallery_loader, device)
    if Eq is None or Eg is None:
        return float("nan")
    pred = yg[(Eq @ Eg.T).argmax(dim=1)]
    return (pred == yq).float().mean().item()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=24)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--margin", type=float, default=0.30)
    ap.add_argument("--scale", type=float, default=30.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)

    s = get_settings()
    device = resolve_device(s.device)
    amostras, classes = coletar(s.images_root)
    if not amostras:
        log.error("nenhuma imagem em %s — rode o scraper primeiro", s.images_root)
        return 1

    treino, val = split(amostras)
    log.info("%d imagens | %d classes | treino=%d val=%d",
             len(amostras), len(classes), len(treino), len(val))
    if len(amostras) / max(len(classes), 1) < 2:
        log.warning("média < 2 imagens por espécie: o treino aprenderá pouco além de "
                    "invariância a augmentation. Adicione fotos de campo por espécie.")

    dl_tr = DataLoader(WoodDataset(treino, s.image_size, True), batch_size=args.batch_size,
                       shuffle=True, num_workers=args.workers, drop_last=len(treino) > args.batch_size)
    dl_va = DataLoader(WoodDataset(val, s.image_size, False), batch_size=args.batch_size,
                       num_workers=args.workers) if val else None
    # galeria de treino SEM augmentation, usada como catálogo na métrica de recall
    dl_ga = DataLoader(WoodDataset(treino, s.image_size, False), batch_size=args.batch_size,
                       num_workers=args.workers) if val else None

    model = XiloArcFaceModel(len(classes), s.backbone, s.embedding_dim,
                             args.scale, args.margin).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    steps = max(len(dl_tr), 1)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    melhor = -1.0
    melhor_epoca = 0
    historico: list[dict] = []
    s.artifacts_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        # ramp-up da margem: margem cheia desde a época 1 costuma colapsar
        model.head.margin = args.margin * min(1.0, epoch / max(args.warmup * 2, 1))
        model.train()
        perda_total = 0.0
        for i, (x, y) in enumerate(dl_tr):
            # warmup linear + cosine decay
            t = (epoch - 1) * steps + i
            total = args.epochs * steps
            warm = args.warmup * steps
            lr = args.lr * (t / max(warm, 1) if t < warm else
                            0.5 * (1 + math.cos(math.pi * (t - warm) / max(total - warm, 1))))
            for g in opt.param_groups:
                g["lr"] = lr

            x, y = x.to(device), y.to(device)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                _, logits = model(x, y)
                loss = F.cross_entropy(logits, y, label_smoothing=0.1)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            scaler.step(opt); scaler.update()
            perda_total += loss.item()

        loss_media = perda_total / steps
        r1 = recall_at_1(model, dl_va, dl_ga, device) if dl_va else float("nan")
        log.info("época %2d/%d | loss %.4f | recall@1 %.4f | margem %.3f",
                 epoch, args.epochs, loss_media, r1, model.head.margin)
        historico.append({
            "epoca": epoch, "loss": round(loss_media, 4),
            "recall_at_1": None if math.isnan(r1) else round(r1, 4),
            "margem": round(model.head.margin, 3),
        })

        # '>=' guarda o modelo MAIS TREINADO em caso de empate (val é pequena);
        # com a métrica corrigida, o recall sobe e o melhor tende à última época.
        if not math.isnan(r1) and r1 >= melhor:
            melhor, melhor_epoca = r1, epoch
            torch.save({"embedder": model.embedder.state_dict(),
                        "classes": classes, "recall_at_1": r1,
                        "backbone": s.backbone, "embedding_dim": s.embedding_dim},
                       s.checkpoint)
            log.info("  ↳ checkpoint salvo (recall@1 %.4f)", r1)

    if melhor < 0:  # sem conjunto de validação: salva a última época
        torch.save({"embedder": model.embedder.state_dict(), "classes": classes,
                    "backbone": s.backbone, "embedding_dim": s.embedding_dim}, s.checkpoint)

    # relatório do treino (para conferência)
    relatorio = {
        "config": {"epochs": args.epochs, "batch_size": args.batch_size, "lr": args.lr,
                   "margin": args.margin, "scale": args.scale, "backbone": s.backbone,
                   "embedding_dim": s.embedding_dim, "device": device.type},
        "dataset": {"imagens": len(amostras), "classes": len(classes),
                    "treino": len(treino), "val": len(val),
                    "obs": "recall@1 medido nas espécies com >=3 fotos (as que têm imagem de validação)"},
        "melhor_recall_at_1": None if melhor < 0 else round(melhor, 4),
        "melhor_epoca": melhor_epoca,
        "historico": historico,
    }
    (s.artifacts_dir / "train_report.json").write_text(
        __import__("json").dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("✔ treino concluído — melhor recall@1: %.4f (época %d) | %s",
             melhor, melhor_epoca, s.checkpoint)
    log.info("relatório: %s", s.artifacts_dir / "train_report.json")
    log.info("Próximo passo: python -m backend.scripts.build_index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
