/**
 * Galeria de imagens da espécie: além da seção comparada, mostra as demais
 * fotos (casca, tora, árvore, outros cortes) — o contexto que aparece depois
 * do resultado, para o usuário confirmar visualmente.
 */
import { useState } from 'react';
import type { ImagemRef } from '../types/xiloscan';
import { TIPO_IMAGEM_LABEL } from '../types/xiloscan';

export interface GaleriaEspecieProps {
  imagens: ImagemRef[];
  nome: string;
}

export function GaleriaEspecie({ imagens, nome }: GaleriaEspecieProps) {
  const [zoom, setZoom] = useState<ImagemRef | null>(null);
  if (!imagens || imagens.length === 0) return null;

  return (
    <section className="xs-galeria">
      <h4 className="xs-galeria__titulo">Imagens da espécie</h4>
      <ul className="xs-galeria__grid">
        {imagens.map((im, i) => (
          <li key={`${im.tipo}-${i}`} className="xs-galeria__item">
            <button
              type="button"
              className="xs-galeria__botao"
              onClick={() => setZoom(im)}
              aria-label={`Ampliar ${TIPO_IMAGEM_LABEL[im.tipo] ?? im.tipo} de ${nome}`}
            >
              <img src={im.url} alt={`${TIPO_IMAGEM_LABEL[im.tipo] ?? im.tipo} — ${nome}`} loading="lazy" />
              <span className="xs-galeria__rotulo">{TIPO_IMAGEM_LABEL[im.tipo] ?? im.tipo}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="xs-galeria__fonte">Fonte das imagens: LPF/SFB</p>

      {zoom && (
        <div
          className="xs-galeria__lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={`${TIPO_IMAGEM_LABEL[zoom.tipo] ?? zoom.tipo} — ${nome}`}
          onClick={() => setZoom(null)}
        >
          <figure className="xs-galeria__figura" onClick={(e) => e.stopPropagation()}>
            <img src={zoom.url} alt={`${TIPO_IMAGEM_LABEL[zoom.tipo] ?? zoom.tipo} — ${nome}`} />
            <figcaption>
              {TIPO_IMAGEM_LABEL[zoom.tipo] ?? zoom.tipo} · <em>{nome}</em>
            </figcaption>
            <button type="button" className="xs-galeria__fechar" onClick={() => setZoom(null)} aria-label="Fechar">
              ✕
            </button>
          </figure>
        </div>
      )}
    </section>
  );
}
