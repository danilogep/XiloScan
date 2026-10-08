"""Carrega o dataset_lpf.json e expõe as espécies como WoodSpecies."""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import SECOES_CORTE, AnatomicalFeatures, ImagemRef, Taxonomia, WoodSpecies

_ANAT_FIELDS = set(AnatomicalFeatures.model_fields)


def _url_estatica(arquivo: str | None) -> str:
    """caminho relativo do dataset (images/<Esp>/<arq>) -> URL servida pelo backend."""
    if not arquivo:
        return ""
    return "/static/" + arquivo.lstrip("/")


# O scraper grava o rótulo longo do LPF ("corte_transversal_macroscopico"); o
# restante do backend fala o vocabulário curto de SECOES_CORTE. A tradução vive
# aqui, na fronteira: sem ela, nenhuma foto é reconhecida como seção de corte,
# o índice sai vazio e a galeria perde a ordenação.
_ALIAS_SECAO = {
    "corte_transversal_macroscopico": "transversal",
    "corte_tangencial_macroscopico": "tangencial",
    "corte_radial_macroscopico": "radial",
    "macroscopico": "transversal",
    "transversal_macroscopico": "transversal",
}


def normaliza_secao(tipo: str | None) -> str:
    """Rótulo de imagem do dataset -> vocabulário de seções do backend."""
    if not tipo:
        return "transversal"
    t = tipo.strip().lower()
    if t in _ALIAS_SECAO:
        return _ALIAS_SECAO[t]
    # Tolera variações não mapeadas: "corte_radial_xyz" ainda contém "radial".
    for secao in SECOES_CORTE:
        if secao in t:
            return secao
    return t


def _galeria(imagens_raw: list[dict]) -> list[ImagemRef]:
    refs: list[ImagemRef] = []
    for im in imagens_raw:
        arq = im.get("arquivo")
        if not arq:
            continue  # imagem que não foi baixada (404 no LPF)
        refs.append(ImagemRef(
            tipo=normaliza_secao(im.get("tipo")),
            url=_url_estatica(arq),
            arquivo=arq,
            fonte_url=im.get("url", ""),
        ))
    # ordena: seções de corte primeiro (transversal, tangencial, radial), depois contexto
    ordem = {t: i for i, t in enumerate(
        ["transversal", "tangencial", "radial", "arvore", "tora", "casca", "madeira"]
    )}
    refs.sort(key=lambda r: ordem.get(r.tipo, 99))
    return refs


def _miniatura(galeria: list[ImagemRef]) -> str | None:
    """thumbnail representativo: prioriza a superfície do lenho, nunca a foto da árvore."""
    for secao in ("transversal", "tangencial", "radial"):
        for r in galeria:
            if r.tipo == secao:
                return r.url
    return galeria[0].url if galeria else None


class Catalog:
    def __init__(self, especies: dict[str, WoodSpecies], meta: dict):
        self._especies = especies
        self.meta = meta

    @classmethod
    def load(cls, path: Path) -> Catalog:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        especies: dict[str, WoodSpecies] = {}
        for e in raw.get("especies", []):
            anat_src = dict(e.get("anatomia_macroscopica", {}))
            anat_src["dominio_fitogeografico"] = (
                e.get("procedencia", {}).get("dominio_fitogeografico") or []
            )
            anat = AnatomicalFeatures(
                **{k: v for k, v in anat_src.items() if k in _ANAT_FIELDS}
            )
            galeria = _galeria(e.get("imagens") or [])
            atalhos = e.get("propriedades_chave") or {}
            especies[e["id"]] = WoodSpecies(
                id=e["id"],
                lpf_id=e.get("lpf_id"),
                fonte_url=e.get("fonte_url", ""),
                taxonomia=Taxonomia(**{
                    k: v for k, v in e.get("taxonomia", {}).items()
                    if k in Taxonomia.model_fields
                }),
                anatomia=anat,
                cor_descricao=e.get("caracteres_gerais", {}).get("cor_descricao", ""),
                gra=e.get("caracteres_gerais", {}).get("gra", ""),
                textura=e.get("caracteres_gerais", {}).get("textura", ""),
                densidade_basica=atalhos.get("densidade_basica"),
                imagem_url=_miniatura(galeria),
                imagens=galeria,
                completeness=float(e.get("completeness", 0.0)),
            )
        return cls(especies, raw.get("meta", {}))

    def get(self, species_id: str) -> WoodSpecies | None:
        return self._especies.get(species_id)

    def all(self) -> list[WoodSpecies]:
        return list(self._especies.values())

    def __len__(self) -> int:
        return len(self._especies)
