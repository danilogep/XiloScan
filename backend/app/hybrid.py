"""
Filtro híbrido hierárquico: similaridade visual × atributos macroscópicos.

Racional: o embedding sozinho confunde espécies de textura parecida, e os
atributos sozinhos não discriminam (dezenas de espécies compartilham
"difusa + vasicêntrico + amarela"). Combinando os dois, o atributo age como
um PRIOR que reordena o ranking visual — sem eliminar candidatos, porque o
usuário erra ao informar atributos e uma eliminação dura esconderia a
espécie correta.

score_final = w_visual * score_visual + w_attr * score_atributos

score_atributos é a média ponderada de concordâncias por campo (pesos vindos
de mcb_taxonomy.json). Campo não informado pelo usuário é NEUTRO: sai do
denominador em vez de contar como divergência. Se o usuário não informar
nada, score_atributos = score_visual (o híbrido vira o visual puro).
"""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import AnatomicalFeatures, FeatureMatch, NivelConfianca

CAMPOS_MULTI = {
    "dominio_fitogeografico", "vasos_agrupamento", "tiloses_substancias",
    "parenquima_apotraqueal", "parenquima_paratraqueal", "raios_visibilidade",
}


class HybridScorer:
    def __init__(self, taxonomy_path: Path, peso_visual: float = 0.70,
                 limiar_alta: float = 0.80, limiar_media: float = 0.60):
        tax = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
        self.pesos: dict[str, float] = {}
        self.rotulos: dict[str, str] = {}
        for cat in tax["categorias"]:
            self.pesos[cat["chave"]] = float(cat.get("peso_filtro_hibrido", 0.1))
            self.rotulos[cat["chave"]] = cat["rotulo"]
        self.peso_visual = peso_visual
        self.peso_atributos = 1.0 - peso_visual
        self.limiar_alta = limiar_alta
        self.limiar_media = limiar_media

    @staticmethod
    def _as_list(v) -> list[str]:
        if v is None:
            return []
        return [x for x in (v if isinstance(v, list) else [v]) if x]

    def compare_features(
        self, usuario: AnatomicalFeatures, especie: AnatomicalFeatures
    ) -> tuple[float, list[FeatureMatch]]:
        detalhes: list[FeatureMatch] = []
        soma_peso = 0.0
        soma_score = 0.0

        for campo, peso in self.pesos.items():
            vu = self._as_list(getattr(usuario, campo, None))
            ve = self._as_list(getattr(especie, campo, None))

            if not vu:
                # usuário não informou -> neutro, não entra no denominador
                detalhes.append(FeatureMatch(
                    campo=campo, rotulo=self.rotulos[campo], valor_usuario=[],
                    valor_especie=ve, status="nao_informado", peso=peso))
                continue

            if not ve:
                # a espécie não tem o dado preenchido (lacuna do overlay MCB):
                # também é neutro — não punimos o usuário por lacuna nossa
                detalhes.append(FeatureMatch(
                    campo=campo, rotulo=self.rotulos[campo], valor_usuario=vu,
                    valor_especie=[], status="nao_informado", peso=peso))
                continue

            if campo in CAMPOS_MULTI:
                inter = set(vu) & set(ve)
                s = len(inter) / len(set(vu))          # cobertura do que o usuário viu
            else:
                s = 1.0 if vu[0] == ve[0] else 0.0

            soma_peso += peso
            soma_score += peso * s
            detalhes.append(FeatureMatch(
                campo=campo, rotulo=self.rotulos[campo], valor_usuario=vu,
                valor_especie=ve, status="coincidente" if s > 0 else "divergente",
                peso=peso))

        score = soma_score / soma_peso if soma_peso > 0 else 0.0
        return score, detalhes

    def combine(self, score_visual: float, score_atributos: float,
                usuario_informou: bool, peso_visual: float | None = None) -> float:
        if not usuario_informou:
            return score_visual
        wv = self.peso_visual if peso_visual is None else peso_visual
        return wv * score_visual + (1.0 - wv) * score_atributos

    def nivel(self, score_final: float) -> NivelConfianca:
        if score_final >= self.limiar_alta:
            return NivelConfianca.ALTA
        if score_final >= self.limiar_media:
            return NivelConfianca.MEDIA
        return NivelConfianca.BAIXA

    @staticmethod
    def usuario_informou(a: AnatomicalFeatures) -> bool:
        return any(
            (v if isinstance(v, list) else [v] if v else [])
            for v in a.model_dump().values()
        )

    @staticmethod
    def top1_ambiguo(scores: list[float], delta: float = 0.05) -> bool:
        return len(scores) >= 2 and (scores[0] - scores[1]) < delta
