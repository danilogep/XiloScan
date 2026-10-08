/**
 * Comparador lado a lado com cortina deslizante.
 *
 * Decisões que importam para o uso real (campo, luva, celular):
 *  - pointer events (funciona com mouse, toque e caneta) + setPointerCapture,
 *    para o arraste não morrer se o dedo sair do elemento;
 *  - teclado: setas movem 2%, Shift+setas 10%, Home/End vão aos extremos —
 *    o divisor é um role="slider" de verdade, não uma div arrastável;
 *  - as duas imagens ficam em 1:1 com object-fit: cover, garantindo que o
 *    mesmo ponto da tela corresponda ao mesmo ponto das duas amostras.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export interface ImageCompareSliderProps {
  antesSrc: string;
  depoisSrc: string;
  antesLabel?: string;
  depoisLabel?: string;
  posicaoInicial?: number;
  altura?: number | string;
  onPosicaoChange?: (pct: number) => void;
}

const clamp = (n: number) => Math.min(100, Math.max(0, n));

export function ImageCompareSlider({
  antesSrc,
  depoisSrc,
  antesLabel = 'Sua amostra',
  depoisLabel = 'Referência LPF',
  posicaoInicial = 50,
  altura = 360,
  onPosicaoChange,
}: ImageCompareSliderProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState(clamp(posicaoInicial));
  const [arrastando, setArrastando] = useState(false);

  const atualizar = useCallback(
    (clientX: number) => {
      const el = containerRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      if (r.width === 0) return;
      const pct = clamp(((clientX - r.left) / r.width) * 100);
      setPos(pct);
      onPosicaoChange?.(pct);
    },
    [onPosicaoChange],
  );

  useEffect(() => {
    if (!arrastando) return;
    const move = (e: PointerEvent) => atualizar(e.clientX);
    const up = () => setArrastando(false);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
    };
  }, [arrastando, atualizar]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const passo = e.shiftKey ? 10 : 2;
    let novo: number | null = null;
    if (e.key === 'ArrowLeft') novo = pos - passo;
    else if (e.key === 'ArrowRight') novo = pos + passo;
    else if (e.key === 'Home') novo = 0;
    else if (e.key === 'End') novo = 100;
    if (novo !== null) {
      e.preventDefault();
      const v = clamp(novo);
      setPos(v);
      onPosicaoChange?.(v);
    }
  };

  return (
    <div
      ref={containerRef}
      className="xs-compare"
      style={{ height: typeof altura === 'number' ? `${altura}px` : altura }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        setArrastando(true);
        atualizar(e.clientX);
      }}
    >
      <img className="xs-compare__img" src={depoisSrc} alt={depoisLabel} draggable={false} />
      <div className="xs-compare__cortina" style={{ width: `${pos}%` }}>
        {/* largura fixa do container: a imagem não deforma ao mover a cortina */}
        <img
          className="xs-compare__img"
          src={antesSrc}
          alt={antesLabel}
          draggable={false}
          style={{ width: containerRef.current?.clientWidth ?? '100%' }}
        />
      </div>

      <span className="xs-compare__tag xs-compare__tag--esq">{antesLabel}</span>
      <span className="xs-compare__tag xs-compare__tag--dir">{depoisLabel}</span>

      <div
        role="slider"
        tabIndex={0}
        aria-label="Posição da comparação entre sua amostra e a referência"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pos)}
        aria-valuetext={`${Math.round(pos)}% da sua amostra visível`}
        className={`xs-compare__handle${arrastando ? ' is-dragging' : ''}`}
        style={{ left: `${pos}%` }}
        onKeyDown={onKeyDown}
      >
        <span className="xs-compare__grip" aria-hidden="true">⇔</span>
      </div>
    </div>
  );
}
