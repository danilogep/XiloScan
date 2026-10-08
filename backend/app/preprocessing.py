"""
Pré-processamento macroscópico.

Objetivo: neutralizar as três fontes de variância que mais derrubam a acurácia
em fotos de campo de corte transversal — iluminação, escala/zoom e
enquadramento — antes de extrair o embedding.

Pipeline:
  1. EXIF-transpose e conversão para RGB
  2. corte central quadrado (remove borda/dedos/fundo)
  3. CLAHE no canal L do LAB (equalização local; preserva cromaticidade)
  4. gray-world white balance (neutraliza dominante amarela de lâmpada)
  5. resize com Lanczos para image_size
  6. normalização ImageNet
"""
from __future__ import annotations

import io

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_rgb(data: bytes | str) -> np.ndarray:
    """Bytes ou caminho -> ndarray RGB uint8, com EXIF já aplicado."""
    if isinstance(data, bytes):
        img = Image.open(io.BytesIO(data))
    else:
        img = Image.open(data)
    img = ImageOps.exif_transpose(img).convert("RGB")
    return np.asarray(img)


def center_crop(img: np.ndarray, ratio: float = 0.85) -> np.ndarray:
    """Corte central quadrado cobrindo `ratio` da menor dimensão."""
    h, w = img.shape[:2]
    side = int(min(h, w) * ratio)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    return img[y0 : y0 + side, x0 : x0 + side]


def apply_clahe(img: np.ndarray, clip_limit: float = 2.5, grid: int = 8) -> np.ndarray:
    """CLAHE apenas na luminância (LAB), preservando a cor da madeira."""
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    luminancia, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid, grid))
    luminancia = clahe.apply(luminancia)
    return cv2.cvtColor(cv2.merge((luminancia, a, b)), cv2.COLOR_LAB2RGB)


def gray_world_wb(img: np.ndarray) -> np.ndarray:
    """
    White balance gray-world. Crítico aqui: a COR é um atributo diagnóstico,
    e fotos sob luz quente deslocam toda a espécie para o bin 'amarela'.
    """
    f = img.astype(np.float32)
    means = f.reshape(-1, 3).mean(axis=0)
    gray = means.mean()
    if gray <= 1e-6:
        return img
    scale = gray / np.clip(means, 1e-6, None)
    return np.clip(f * scale, 0, 255).astype(np.uint8)


def preprocess(
    data: bytes | str,
    image_size: int = 380,
    clip_limit: float = 2.5,
    grid: int = 8,
    crop_ratio: float = 0.85,
    white_balance: bool = True,
) -> np.ndarray:
    """Retorna float32 CHW normalizado ImageNet."""
    img = load_rgb(data)
    img = center_crop(img, crop_ratio)
    if white_balance:
        img = gray_world_wb(img)
    img = apply_clahe(img, clip_limit, grid)
    img = cv2.resize(img, (image_size, image_size), interpolation=cv2.INTER_LANCZOS4)
    arr = img.astype(np.float32) / 255.0
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(arr, (2, 0, 1))


def to_batch(arrays: list[np.ndarray]) -> torch.Tensor:
    return torch.from_numpy(np.stack(arrays)).float()


def tta_variants(chw: np.ndarray) -> list[np.ndarray]:
    """
    O corte transversal não tem orientação canônica: a mesma amostra
    fotografada girada deve cair no mesmo ponto do espaço de embeddings.
    4 rotações + flip horizontal = 8 vistas; a média L2-normalizada é o
    embedding final.
    """
    out: list[np.ndarray] = []
    hwc = np.transpose(chw, (1, 2, 0))
    for k in range(4):
        rot = np.rot90(hwc, k)
        out.append(np.ascontiguousarray(np.transpose(rot, (2, 0, 1))))
        out.append(np.ascontiguousarray(np.transpose(np.fliplr(rot), (2, 0, 1))))
    return out


def quality_report(data: bytes | str) -> dict:
    """
    Checagem barata de qualidade antes de gastar inferência.
    Devolve avisos acionáveis para o componente de captura do frontend.
    """
    img = load_rgb(data)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brilho = float(gray.mean())
    saturados = float((gray >= 250).mean())

    avisos: list[str] = []
    if min(h, w) < 512:
        avisos.append("Resolução baixa: fotografe mais perto ou com câmera melhor (mín. 512 px).")
    if blur < 80:
        avisos.append("Imagem desfocada: apoie a amostra e toque para focar.")
    if brilho < 55:
        avisos.append("Imagem escura: aumente a iluminação difusa.")
    if brilho > 210 or saturados > 0.08:
        avisos.append("Imagem estourada: evite flash direto e reflexo.")
    return {
        "largura": w, "altura": h,
        "nitidez_laplaciana": round(blur, 1),
        "brilho_medio": round(brilho, 1),
        "pct_saturado": round(saturados, 4),
        "aceitavel": not avisos,
        "avisos": avisos,
    }
