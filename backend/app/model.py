"""
Extrator de características para metric learning.

Por que ArcFace e não softmax comum: com 157 classes e poucas imagens por
espécie, o que precisamos não é um classificador fechado, e sim um espaço
métrico onde amostras da mesma espécie fiquem próximas e o sistema aceite
espécies novas sem retreinar. ArcFace impõe margem angular aditiva na
hiperesfera, o que separa classes visualmente parecidas (o caso das
Lauraceae/Sapotaceae, que confundem softmax) melhor que Triplet Loss —
e sem a engenharia de mineração de tripletas.
"""
from __future__ import annotations

import math
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F


def resolve_device(pref: str = "auto") -> torch.device:
    if pref != "auto":
        return torch.device(pref)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class GeM(nn.Module):
    """
    Generalized Mean Pooling. Em textura (que é o sinal aqui, não forma),
    GeM supera o average pooling: pondera as ativações mais fortes sem
    colapsar como o max pooling.
    """

    def __init__(self, p: float = 3.0, eps: float = 1e-6):
        super().__init__()
        self.p = nn.Parameter(torch.ones(1) * p)
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.clamp(min=self.eps).pow(self.p)
        x = F.adaptive_avg_pool2d(x, 1)
        return x.pow(1.0 / self.p).flatten(1)


class ArcMarginProduct(nn.Module):
    """Cabeça ArcFace (Deng et al., 2019). Usada só no treino."""

    def __init__(self, in_features: int, out_features: int, scale: float = 30.0, margin: float = 0.30):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)
        self.scale = scale
        self.margin = margin
        self.cos_m = math.cos(margin)
        self.sin_m = math.sin(margin)
        self.th = math.cos(math.pi - margin)
        self.mm = math.sin(math.pi - margin) * margin

    def forward(self, embeddings: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        cosine = F.linear(F.normalize(embeddings), F.normalize(self.weight)).clamp(-1 + 1e-7, 1 - 1e-7)
        sine = torch.sqrt(1.0 - cosine.pow(2))
        phi = cosine * self.cos_m - sine * self.sin_m
        phi = torch.where(cosine > self.th, phi, cosine - self.mm)
        one_hot = torch.zeros_like(cosine).scatter_(1, labels.view(-1, 1), 1.0)
        return self.scale * (one_hot * phi + (1.0 - one_hot) * cosine)


class XiloEmbedder(nn.Module):
    """Backbone (timm) + GeM + BNNeck + projeção linear para `embedding_dim`."""

    def __init__(
        self,
        backbone: str = "tf_efficientnet_b4",
        embedding_dim: int = 512,
        pretrained: bool = True,
        dropout: float = 0.2,
    ):
        super().__init__()
        import timm

        self.backbone_name = backbone
        self.backbone = timm.create_model(backbone, pretrained=pretrained, num_classes=0, global_pool="")
        feat_dim = self.backbone.num_features
        self.pool = GeM()
        self.dropout = nn.Dropout(dropout)
        self.neck = nn.Linear(feat_dim, embedding_dim)
        self.bn = nn.BatchNorm1d(embedding_dim)
        self.embedding_dim = embedding_dim

    def forward(self, x: torch.Tensor, normalize: bool = True) -> torch.Tensor:
        feats = self.backbone.forward_features(x)
        if feats.ndim == 3:  # backbones ViT-like: (B, N, C) -> (B, C, H, W)
            b, n, c = feats.shape
            s = int(n ** 0.5)
            feats = feats[:, -s * s :, :].transpose(1, 2).reshape(b, c, s, s)
        x = self.pool(feats)
        x = self.bn(self.neck(self.dropout(x)))
        return F.normalize(x, dim=1) if normalize else x


class XiloArcFaceModel(nn.Module):
    """Wrapper de treino: embedder + cabeça ArcFace."""

    def __init__(self, n_classes: int, backbone: str = "tf_efficientnet_b4",
                 embedding_dim: int = 512, scale: float = 30.0, margin: float = 0.30,
                 pretrained: bool = True):
        super().__init__()
        self.embedder = XiloEmbedder(backbone, embedding_dim, pretrained=pretrained)
        self.head = ArcMarginProduct(embedding_dim, n_classes, scale, margin)

    def forward(self, x: torch.Tensor, labels: torch.Tensor | None = None):
        emb = self.embedder(x)
        if labels is None:
            return emb
        return emb, self.head(emb, labels)


@torch.inference_mode()
def embed_batch(model: XiloEmbedder, batch: torch.Tensor, device: torch.device) -> torch.Tensor:
    model.eval()
    out = model(batch.to(device))
    return out.detach().cpu()


def load_embedder(checkpoint: Path | None, backbone: str, embedding_dim: int,
                  device: torch.device) -> tuple[XiloEmbedder, bool]:
    """
    Carrega o embedder. Se não houver checkpoint treinado, cai para os pesos
    ImageNet — funciona como baseline, mas a acurácia é MUITO inferior:
    trate `treinado=False` como modo de desenvolvimento.
    """
    treinado = bool(checkpoint and Path(checkpoint).exists())
    model = XiloEmbedder(backbone, embedding_dim, pretrained=not treinado)
    if treinado:
        state = torch.load(checkpoint, map_location="cpu")
        state = state.get("embedder", state.get("model", state))
        model.load_state_dict(state, strict=False)
    return model.to(device).eval(), treinado
