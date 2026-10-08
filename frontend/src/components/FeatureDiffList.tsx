/**
 * Lista de características anatômicas coincidentes vs. divergentes.
 *
 * Três estados, nunca dois: "não informado" é diferente de "divergente".
 * Um campo que o usuário não preencheu — ou que falta no dataset — não
 * conta contra a espécie, e a interface precisa dizer isso, senão o
 * usuário lê ausência de dado como discordância.
 */
import type { FeatureMatch, FeatureStatus } from '../types/xiloscan';

const ICONE: Record<FeatureStatus, string> = {
  coincidente: '✓',
  divergente: '✕',
  nao_informado: '–',
};

const TEXTO: Record<FeatureStatus, string> = {
  coincidente: 'Coincidente',
  divergente: 'Divergente',
  nao_informado: 'Não informado',
};

export interface FeatureDiffListProps {
  features: FeatureMatch[];
  mostrarNaoInformados?: boolean;
  dicionario?: Record<string, string>;
}

export function FeatureDiffList({
  features,
  mostrarNaoInformados = false,
  dicionario = {},
}: FeatureDiffListProps) {
  const rotular = (codigos: string[]) =>
    codigos.length ? codigos.map((c) => dicionario[c] ?? c).join(', ') : '—';

  const ordem: Record<FeatureStatus, number> = { divergente: 0, coincidente: 1, nao_informado: 2 };
  const visiveis = features
    .filter((f) => mostrarNaoInformados || f.status !== 'nao_informado')
    .sort((a, b) => ordem[a.status] - ordem[b.status] || b.peso - a.peso);

  if (!visiveis.length) {
    return (
      <p className="xs-feat__vazio">
        Nenhum atributo anatômico informado — o resultado usou apenas a similaridade visual.
      </p>
    );
  }

  return (
    <ul className="xs-feat">
      {visiveis.map((f) => (
        <li key={f.campo} className={`xs-feat__item xs-feat__item--${f.status}`}>
          <span className="xs-feat__icone" aria-hidden="true">{ICONE[f.status]}</span>
          <div className="xs-feat__corpo">
            <span className="xs-feat__rotulo">{f.rotulo}</span>
            <span className="xs-feat__valores">
              <span className="xs-feat__usuario">
                Você: <strong>{rotular(f.valor_usuario)}</strong>
              </span>
              <span className="xs-feat__sep" aria-hidden="true">·</span>
              <span className="xs-feat__especie">
                Espécie: <strong>{rotular(f.valor_especie)}</strong>
              </span>
            </span>
          </div>
          <span className="xs-sr-only">{TEXTO[f.status]}</span>
        </li>
      ))}
    </ul>
  );
}
