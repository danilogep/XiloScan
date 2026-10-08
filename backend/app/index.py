"""
Banco vetorial FAISS.

Escolha: IndexFlatIP sobre vetores L2-normalizados == similaridade de cosseno
exata. Com 157 espécies × ~5-40 imagens, são no máximo alguns milhares de
vetores — busca exata custa microssegundos e evita a perda de recall do
IVF/PQ. O caminho `ivf_pq` fica pronto para quando o acervo crescer com
fotos de campo dos usuários.

Agregação: cada espécie tem N vetores (imagem oficial + augmentations/fotos).
O score da espécie é o MÁXIMO entre seus vetores, não a média — uma amostra
que casa perfeitamente com uma das vistas não deve ser penalizada pelas outras.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import faiss
import numpy as np

log = logging.getLogger("xiloscan.index")

_SECOES = ("transversal", "tangencial", "radial", "arvore", "tora", "casca", "madeira")


def _tipo_de_path(caminho: str) -> str:
    """deriva a seção do nome do arquivo <especie>_<tipo>_NN.jpg (fallback)."""
    nome = Path(caminho).stem.lower()
    for secao in _SECOES:
        if f"_{secao}_" in nome or nome.endswith(f"_{secao}"):
            return secao
    return "transversal"


class VectorIndex:
    def __init__(self, dim: int, index_type: str = "flat_ip"):
        self.dim = dim
        self.index_type = index_type
        self.index: faiss.Index | None = None
        self.species_ids: list[str] = []      # species_id por vetor
        self.image_paths: list[str] = []      # imagem de origem por vetor
        self.tipos: list[str] = []            # seção (transversal/tangencial/...) por vetor

    # ────────────────────────────────────────────────────────────── build

    def build(
        self,
        vectors: np.ndarray,
        species_ids: list[str],
        image_paths: list[str],
        tipos: list[str] | None = None,
    ) -> None:
        if vectors.ndim != 2 or vectors.shape[1] != self.dim:
            raise ValueError(f"esperado (N,{self.dim}), recebido {vectors.shape}")
        if len(species_ids) != len(vectors):
            raise ValueError("species_ids e vectors com tamanhos diferentes")
        if tipos is None:
            tipos = [_tipo_de_path(p) for p in image_paths]

        vectors = np.ascontiguousarray(vectors.astype(np.float32))
        faiss.normalize_L2(vectors)

        n = len(vectors)
        if self.index_type == "ivf_pq" and n >= 4096:
            nlist = min(int(4 * np.sqrt(n)), n // 39)
            quantizer = faiss.IndexFlatIP(self.dim)
            idx = faiss.IndexIVFPQ(quantizer, self.dim, nlist, 64, 8, faiss.METRIC_INNER_PRODUCT)
            idx.train(vectors)
            idx.nprobe = max(8, nlist // 16)
        else:
            if self.index_type == "ivf_pq":
                log.warning("poucos vetores (%d) para IVF-PQ; usando IndexFlatIP", n)
            idx = faiss.IndexFlatIP(self.dim)

        idx.add(vectors)
        self.index = idx
        self.species_ids = list(species_ids)
        self.image_paths = list(image_paths)
        self.tipos = list(tipos)
        log.info("índice construído: %d vetores, %d espécies", n, len(set(species_ids)))

    # ─────────────────────────────────────────────────────────────── search

    def search_species(
        self,
        query: np.ndarray,
        top_k: int = 10,
        secoes: set[str] | None = None,
    ) -> list[tuple[str, float, str]]:
        """
        Busca e agrega por espécie (max-pooling dos scores).
        Retorna [(species_id, score_cosseno_0a1, imagem_mais_parecida)].

        Se `secoes` for dado, só vetores dessas seções (ex.: {'transversal'})
        entram na comparação — uma foto transversal casa só com transversais.
        """
        if self.index is None:
            raise RuntimeError("índice não construído/carregado")
        q = np.ascontiguousarray(query.astype(np.float32).reshape(1, -1))
        faiss.normalize_L2(q)

        filtrar = bool(secoes) and bool(self.tipos)
        # com filtro, varre tudo para não perder vetores da seção; senão, busca ampla
        if filtrar:
            k = len(self.species_ids)
        else:
            k = min(len(self.species_ids), max(top_k * 12, 64))
        scores, idxs = self.index.search(q, k)

        melhor: dict[str, tuple[float, str]] = {}
        for score, i in zip(scores[0], idxs[0], strict=False):
            if i < 0:
                continue
            if filtrar and self.tipos[i] not in secoes:
                continue
            sid = self.species_ids[i]
            # cosseno ∈ [-1,1] -> [0,1]
            s = float((score + 1.0) / 2.0)
            if sid not in melhor or s > melhor[sid][0]:
                melhor[sid] = (s, self.image_paths[i])

        ordenado = sorted(melhor.items(), key=lambda kv: kv[1][0], reverse=True)
        return [(sid, s, img) for sid, (s, img) in ordenado[:top_k]]

    # ────────────────────────────────────────────────────────── persistência

    def save(self, index_path: Path, meta_path: Path) -> None:
        if self.index is None:
            raise RuntimeError("nada para salvar")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_path))
        meta_path.write_text(
            json.dumps(
                {
                    "dim": self.dim,
                    "index_type": self.index_type,
                    "n_vectors": len(self.species_ids),
                    "species_ids": self.species_ids,
                    "image_paths": self.image_paths,
                    "tipos": self.tipos,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        log.info("índice salvo em %s", index_path)

    @classmethod
    def load(cls, index_path: Path, meta_path: Path) -> VectorIndex:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        obj = cls(meta["dim"], meta.get("index_type", "flat_ip"))
        obj.index = faiss.read_index(str(index_path))
        obj.species_ids = meta["species_ids"]
        obj.image_paths = meta["image_paths"]
        obj.tipos = meta.get("tipos") or [_tipo_de_path(p) for p in obj.image_paths]
        if obj.index.ntotal != len(obj.species_ids):
            raise RuntimeError(
                f"índice inconsistente: {obj.index.ntotal} vetores vs "
                f"{len(obj.species_ids)} labels — reconstrua com build_index.py"
            )
        return obj

    @property
    def n_species(self) -> int:
        return len(set(self.species_ids))

    @property
    def n_vectors(self) -> int:
        return len(self.species_ids)
