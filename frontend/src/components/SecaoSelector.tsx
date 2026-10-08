/**
 * Seletor da seção da foto do usuário.
 *
 * A comparação visual é restrita à seção escolhida: uma foto transversal casa
 * só com imagens transversais, uma tangencial só com tangenciais. Por isso a
 * escolha é obrigatória antes de identificar — ela muda o conjunto comparado.
 */
import type { SecaoCorte } from '../types/xiloscan';

const OPCOES: { valor: SecaoCorte; titulo: string; ajuda: string }[] = [
  { valor: 'transversal', titulo: 'Transversal', ajuda: 'Corte de topo — anéis, poros e parênquima' },
  { valor: 'tangencial', titulo: 'Tangencial', ajuda: 'Face lateral — figura, veios e raios' },
];

export interface SecaoSelectorProps {
  valor: SecaoCorte;
  onChange: (s: SecaoCorte) => void;
  desabilitado?: boolean;
}

export function SecaoSelector({ valor, onChange, desabilitado = false }: SecaoSelectorProps) {
  return (
    <fieldset className="xs-secao" disabled={desabilitado}>
      <legend className="xs-secao__legenda">Qual seção você fotografou?</legend>
      <div className="xs-secao__opcoes" role="radiogroup" aria-label="Seção da foto">
        {OPCOES.map((o) => {
          const ativo = valor === o.valor;
          return (
            <button
              key={o.valor}
              type="button"
              role="radio"
              aria-checked={ativo}
              className={`xs-secao__opcao${ativo ? ' is-ativo' : ''}`}
              onClick={() => onChange(o.valor)}
            >
              <span className="xs-secao__titulo">{o.titulo}</span>
              <span className="xs-secao__ajuda">{o.ajuda}</span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
