"""Contratos da API — espelham 1:1 as interfaces TypeScript do frontend."""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class NivelConfianca(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class AnatomicalFeatures(BaseModel):
    """Descritores macroscópicos no vocabulário controlado do MCB."""
    dominio_fitogeografico: list[str] = Field(default_factory=list)
    cor_madeira: str | None = None
    aneis_crescimento: str | None = None
    vasos_porosidade: str | None = None
    vasos_agrupamento: list[str] = Field(default_factory=list)
    vasos_obstrucao: str | None = None
    tiloses_substancias: list[str] = Field(default_factory=list)
    parenquima_axial: str | None = None
    parenquima_apotraqueal: list[str] = Field(default_factory=list)
    parenquima_paratraqueal: list[str] = Field(default_factory=list)
    raios_visibilidade: list[str] = Field(default_factory=list)


class Taxonomia(BaseModel):
    nome_cientifico: str
    autor: str = ""
    familia: str = ""
    sinonimos: list[str] = Field(default_factory=list)
    nomes_populares: list[str] = Field(default_factory=list)


# seções que servem à comparação visual (vistas do lenho); as demais
# (arvore, tora, casca, madeira) são só contexto para o detalhe da espécie.
SECOES_CORTE = ("transversal", "tangencial", "radial")


class ImagemRef(BaseModel):
    """Uma foto da espécie, com a seção a que pertence."""
    tipo: str = "transversal"   # arvore|tora|casca|tangencial|radial|transversal|madeira
    url: str = ""               # servível pelo backend (/static/images/...)
    arquivo: str = ""           # caminho relativo local (images/<Especie>/<arquivo>)
    fonte_url: str = ""         # URL original no LPF


class WoodSpecies(BaseModel):
    id: str
    lpf_id: int | None = None
    fonte_url: str = ""
    taxonomia: Taxonomia
    anatomia: AnatomicalFeatures
    cor_descricao: str = ""
    gra: str = ""
    textura: str = ""
    densidade_basica: float | None = None
    imagem_url: str | None = None
    imagens: list[ImagemRef] = Field(default_factory=list)
    completeness: float = 0.0


class FeatureMatch(BaseModel):
    campo: str
    rotulo: str
    valor_usuario: list[str]
    valor_especie: list[str]
    status: Literal["coincidente", "divergente", "nao_informado"]
    peso: float


class SpeciesMatch(BaseModel):
    especie: WoodSpecies
    score_visual: float = Field(ge=0.0, le=1.0, description="similaridade de cosseno normalizada")
    score_atributos: float = Field(ge=0.0, le=1.0)
    score_final: float = Field(ge=0.0, le=1.0)
    confianca_pct: float = Field(ge=0.0, le=100.0)
    nivel: NivelConfianca
    features: list[FeatureMatch] = Field(default_factory=list)
    imagem_referencia_url: str | None = None


class ComparisonResult(BaseModel):
    request_id: str
    imagem_usuario_url: str
    processado_em_ms: int
    secao_consultada: str | None = None
    matches: list[SpeciesMatch]
    top1_ambiguo: bool = Field(
        default=False,
        description="True quando a diferença entre o 1º e o 2º score < 0.05 — exige confirmação humana.",
    )
    aviso: str = (
        "Resultado auxiliar. A identificação macroscópica de madeira exige confirmação "
        "por profissional habilitado; não use isoladamente para fins periciais ou legais."
    )


class IdentifyOptions(BaseModel):
    top_k: int = Field(default=10, ge=1, le=50)
    peso_visual: float | None = Field(default=None, ge=0.0, le=1.0)
    atributos: AnatomicalFeatures = Field(default_factory=AnatomicalFeatures)
    secao: Literal["transversal", "tangencial", "radial"] | None = Field(
        default=None,
        description="Seção da foto do usuário; restringe a comparação às imagens da mesma seção.",
    )


class HealthResponse(BaseModel):
    status: Literal["ok", "degradado"]
    modelo_carregado: bool
    indice_carregado: bool
    n_especies: int
    n_vetores: int
    device: str
    backbone: str
