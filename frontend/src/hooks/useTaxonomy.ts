import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { Taxonomy, TaxonomyCategory } from '../types/xiloscan';

/** Carrega o vocabulário controlado e monta o dicionário código -> rótulo. */
export function useTaxonomy() {
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    const ac = new AbortController();
    api
      .taxonomy(ac.signal)
      .then(setTaxonomy)
      .catch((e: unknown) => {
        if (!ac.signal.aborted) setErro(e instanceof Error ? e.message : 'Falha ao carregar a taxonomia');
      })
      .finally(() => { if (!ac.signal.aborted) setCarregando(false); });
    return () => ac.abort();
  }, []);

  const categorias: TaxonomyCategory[] = useMemo(() => taxonomy?.categorias ?? [], [taxonomy]);

  const dicionario = useMemo(() => {
    const d: Record<string, string> = {};
    for (const c of categorias) for (const o of c.opcoes) d[o.codigo] = o.rotulo;
    return d;
  }, [categorias]);

  return { taxonomy, categorias, dicionario, carregando, erro };
}
