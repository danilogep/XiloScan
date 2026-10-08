/**
 * Card de resultado: índice de confiança + comparador + divergências.
 *
 * O número sozinho engana. Em identificação de madeira um "87%" pode vir
 * de um match visual forte contra uma espécie cujos atributos o usuário
 * marcou como divergentes — então o card sempre mostra a decomposição
 * (visual × atributos) e destaca quando o 1º e o 2º lugar estão empatados.
 */
import { useState } from 'react';
import { ImageCompareSlider } from './ImageCompareSlider';
import { FeatureDiffList } from './FeatureDiffList';
import { GaleriaEspecie } from './GaleriaEspecie';
import type { NivelConfianca, SpeciesMatch } from '../types/xiloscan';
import { nomeCompleto } from '../types/xiloscan';

const NIVEL_TEXTO: Record<NivelConfianca, string> = {
  alta: 'Confiança alta',
  media: 'Confiança média — confirme os atributos',
  baixa: 'Confiança baixa — não conclusivo',
};

export interface ConfidenceCardProps {
  match: SpeciesMatch;
  imagemUsuarioUrl: string;
  posicao: number;
  ambiguo?: boolean;
  dicionario?: Record<string, string>;
  expandidoInicial?: boolean;
}

export function ConfidenceCard({
  match, imagemUsuarioUrl, posicao, ambiguo = false,
  dicionario = {}, expandidoInicial = false,
}: ConfidenceCardProps) {
  const [aberto, setAberto] = useState(expandidoInicial || posicao === 1);
  const [todosAtributos, setTodosAtributos] = useState(false);
  const { especie, confianca_pct, nivel } = match;
  const painelId = `xs-card-painel-${especie.id}`;

  const divergentes = match.features.filter((f) => f.status === 'divergente').length;
  const coincidentes = match.features.filter((f) => f.status === 'coincidente').length;

  return (
    <article className={`xs-card xs-card--${nivel}`}>
      <header className="xs-card__head">
        <span className="xs-card__pos" aria-label={`Posição ${posicao}`}>#{posicao}</span>

        <div className="xs-card__id">
          <h3 className="xs-card__nome">
            <em>{especie.taxonomia.nome_cientifico}</em>
            {especie.taxonomia.autor && <span className="xs-card__autor"> {especie.taxonomia.autor}</span>}
          </h3>
          {especie.taxonomia.nomes_populares.length > 0 && (
            <p className="xs-card__populares">{especie.taxonomia.nomes_populares.join(', ')}</p>
          )}
          {especie.taxonomia.familia && <p className="xs-card__familia">{especie.taxonomia.familia}</p>}
        </div>

        <Medidor pct={confianca_pct} nivel={nivel} />
      </header>

      <p className={`xs-card__nivel xs-card__nivel--${nivel}`}>{NIVEL_TEXTO[nivel]}</p>

      {ambiguo && posicao === 1 && (
        <p className="xs-msg xs-msg--aviso" role="alert">
          Resultado ambíguo: o 2º colocado está a menos de 5 pontos. Compare as duas
          espécies antes de concluir.
        </p>
      )}

      <dl className="xs-card__scores">
        <div><dt>Similaridade visual</dt><dd>{(match.score_visual * 100).toFixed(1)}%</dd></div>
        <div><dt>Atributos anatômicos</dt><dd>{(match.score_atributos * 100).toFixed(1)}%</dd></div>
        <div><dt>Coincidentes / divergentes</dt><dd>{coincidentes} / {divergentes}</dd></div>
      </dl>

      {especie.completeness < 0.5 && (
        <p className="xs-msg xs-msg--info">
          Descritores anatômicos incompletos para esta espécie ({Math.round(especie.completeness * 100)}%):
          o cruzamento por atributos pesou menos aqui.
        </p>
      )}

      <button
        type="button"
        className="xs-card__toggle"
        aria-expanded={aberto}
        aria-controls={painelId}
        onClick={() => setAberto((v) => !v)}
      >
        {aberto ? 'Ocultar comparação' : 'Comparar lado a lado'}
      </button>

      <div id={painelId} hidden={!aberto} className="xs-card__painel">
        {match.imagem_referencia_url ? (
          <ImageCompareSlider
            antesSrc={imagemUsuarioUrl}
            depoisSrc={match.imagem_referencia_url}
            depoisLabel={`Referência LPF — ${especie.taxonomia.nome_cientifico}`}
          />
        ) : (
          <p className="xs-msg xs-msg--info">Sem imagem de referência baixada para esta espécie.</p>
        )}

        <div className="xs-card__featHead">
          <h4>Características anatômicas</h4>
          <label className="xs-card__switch">
            <input
              type="checkbox"
              checked={todosAtributos}
              onChange={(e) => setTodosAtributos(e.target.checked)}
            />
            Mostrar não informados
          </label>
        </div>

        <FeatureDiffList
          features={match.features}
          mostrarNaoInformados={todosAtributos}
          dicionario={dicionario}
        />

        <GaleriaEspecie
          imagens={especie.imagens}
          nome={especie.taxonomia.nome_cientifico}
        />

        <footer className="xs-card__rodape">
          {especie.densidade_basica != null && (
            <span>Densidade básica: {especie.densidade_basica.toFixed(2)} g/cm³</span>
          )}
          {especie.textura && <span>Textura: {especie.textura}</span>}
          {especie.gra && <span>Grã: {especie.gra}</span>}
          {especie.fonte_url && (
            <a href={especie.fonte_url} target="_blank" rel="noopener noreferrer">
              Ficha completa no LPF/SFB ↗
            </a>
          )}
        </footer>
      </div>

      <p className="xs-sr-only">
        {nomeCompleto(especie.taxonomia)}, {confianca_pct.toFixed(1)} por cento de confiança.
      </p>
    </article>
  );
}

function Medidor({ pct, nivel }: { pct: number; nivel: NivelConfianca }) {
  const R = 26;
  const C = 2 * Math.PI * R;
  const preenchido = (Math.min(Math.max(pct, 0), 100) / 100) * C;
  return (
    <div
      className={`xs-medidor xs-medidor--${nivel}`}
      role="meter"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Índice de confiança"
    >
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="32" cy="32" r={R} className="xs-medidor__trilha" />
        <circle
          cx="32" cy="32" r={R}
          className="xs-medidor__arco"
          strokeDasharray={`${preenchido} ${C - preenchido}`}
          transform="rotate(-90 32 32)"
        />
      </svg>
      <span className="xs-medidor__valor">{pct.toFixed(0)}<small>%</small></span>
    </div>
  );
}
