"""Configuração central do XiloScan (12-factor via pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XILOSCAN_", env_file=".env", extra="ignore")

    # ── dados
    dataset_path: Path = ROOT / "data" / "dataset_lpf.json"
    taxonomy_path: Path = ROOT / "data" / "mcb_taxonomy.json"
    images_root: Path = ROOT / "data" / "images"
    artifacts_dir: Path = ROOT / "backend" / "artifacts"

    # ── modelo
    backbone: str = "tf_efficientnet_b4"          # timm; alternativa: "resnet50"
    embedding_dim: int = 512
    image_size: int = 380                          # nativo da B4
    checkpoint: Path = ROOT / "backend" / "artifacts" / "arcface_b4.pt"
    device: str = "auto"                           # auto | cuda | cpu | mps

    # ── índice vetorial
    index_path: Path = ROOT / "backend" / "artifacts" / "xiloscan.faiss"
    index_meta_path: Path = ROOT / "backend" / "artifacts" / "xiloscan_index.json"
    index_type: str = "flat_ip"                    # flat_ip | ivf_pq (>50k vetores)
    top_k: int = 10

    # ── pré-processamento
    clahe_clip_limit: float = 2.5
    clahe_grid: int = 8
    center_crop_ratio: float = 0.85
    tta_enabled: bool = True                       # média de embeddings de 4 rotações

    # ── filtro híbrido
    peso_visual: float = 0.70
    peso_atributos: float = 0.30
    limiar_alta_confianca: float = 0.80
    limiar_media_confianca: float = 0.60

    # ── API
    max_upload_mb: int = 12
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
