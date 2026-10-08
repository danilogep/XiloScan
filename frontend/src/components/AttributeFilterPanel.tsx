/**
 * Formulário de atributos macroscópicos, gerado a partir de /taxonomy.
 *
 * Nada é hard-coded: as categorias, opções e cardinalidades vêm do backend
 * (data/mcb_taxonomy.json). Corrigir um rótulo do vocabulário MCB é editar
 * um JSON, não recompilar o frontend.
 *
 * Categorias com `depende_de` (parênquima apotraqueal/paratraqueal) só
 * aparecem quando a categoria-pai tem o valor correspondente — replicando a
 * hierarquia do app MCB e evitando combinações anatomicamente impossíveis.
 */
import type {
  AnatomicalFeatures, AnatomicalField, TaxonomyCategory,
} from '../types/xiloscan';
import { contaAtributosInformados } from '../types/xiloscan';

export interface AttributeFilterPanelProps {
  categorias: TaxonomyCategory[];
  valores: Partial<AnatomicalFeatures>;
  onChange: (v: Partial<AnatomicalFeatures>) => void;
  desabilitado?: boolean;
}

export function AttributeFilterPanel({
  categorias, valores, onChange, desabilitado = false,
}: AttributeFilterPanelProps) {
  const visivel = (cat: TaxonomyCategory) => {
    if (!cat.depende_de) return true;
    const pai = valores[cat.depende_de.chave];
    const lista = Array.isArray(pai) ? pai : pai ? [pai] : [];
    return lista.includes(cat.depende_de.valor as never);
  };

  const setSingle = (campo: AnatomicalField, codigo: string) => {
    const atual = valores[campo];
    onChange({ ...valores, [campo]: atual === codigo ? null : codigo });
  };

  const toggleMulti = (campo: AnatomicalField, codigo: string) => {
    const atual = (valores[campo] as string[] | undefined) ?? [];
    const novo = atual.includes(codigo) ? atual.filter((c) => c !== codigo) : [...atual, codigo];
    onChange({ ...valores, [campo]: novo });
  };

  const marcado = (campo: AnatomicalField, codigo: string) => {
    const v = valores[campo];
    return Array.isArray(v) ? v.includes(codigo as never) : v === codigo;
  };

  const informados = contaAtributosInformados(valores);

  return (
    <section className="xs-filtros">
      <header className="xs-filtros__head">
        <h2>Atributos macroscópicos <span className="xs-filtros__opcional">(opcional)</span></h2>
        <p className="xs-filtros__ajuda">
          Informe só o que você tem certeza de ter observado. Campo em branco é
          neutro — não penaliza nenhuma espécie. Cada atributo informado reordena
          o ranking visual.
        </p>
        {informados > 0 && (
          <button type="button" className="xs-btn xs-btn--texto" disabled={desabilitado}
                  onClick={() => onChange({})}>
            Limpar {informados} {informados === 1 ? 'atributo' : 'atributos'}
          </button>
        )}
      </header>

      {categorias.filter(visivel).map((cat) => (
        <fieldset key={cat.chave} className="xs-filtros__grupo" disabled={desabilitado}>
          <legend>
            {cat.rotulo}
            <span className="xs-filtros__tipo">
              {cat.multivalorado ? 'múltipla escolha' : 'escolha única'}
            </span>
          </legend>
          <div className="xs-filtros__opcoes">
            {cat.opcoes.map((op) => {
              const sel = marcado(cat.chave, op.codigo);
              return (
                <button
                  key={op.codigo}
                  type="button"
                  className={`xs-chip${sel ? ' is-sel' : ''}`}
                  aria-pressed={sel}
                  title={op.nota ?? op.rotulo}
                  onClick={() =>
                    cat.multivalorado
                      ? toggleMulti(cat.chave, op.codigo)
                      : setSingle(cat.chave, op.codigo)
                  }
                >
                  {op.hex_referencia && (
                    <span className="xs-chip__cor" style={{ background: op.hex_referencia }} aria-hidden="true" />
                  )}
                  {op.rotulo}
                  {op.confianca === 'inferido' && (
                    <span className="xs-chip__flag" title="Rótulo a conferir no glossário do app MCB">*</span>
                  )}
                </button>
              );
            })}
          </div>
        </fieldset>
      ))}
      <p className="xs-filtros__nota">
        * termo ainda não conferido contra o Glossário do app MCB.
      </p>
    </section>
  );
}
