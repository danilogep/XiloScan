/**
 * Captura/upload da imagem macroscópica com guia visual de centralização.
 *
 * A guia não é decorativa: o backend faz corte central de 85%, então o que
 * estiver fora do quadrado tracejado é DESCARTADO antes da inferência. A
 * moldura mostra exatamente essa região, e a régua de escala orienta o
 * enquadramento (~2 cm de face, que é a escala em que os poros ficam
 * resolvíveis a olho nu).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, XiloScanError } from '../api/client';
import type { QualityReport } from '../types/xiloscan';

export interface CaptureUploaderProps {
  onArquivo: (file: File, previewUrl: string, qualidade: QualityReport | null) => void;
  desabilitado?: boolean;
  maxMB?: number;
}

const ACEITOS = ['image/jpeg', 'image/png', 'image/webp'];

export function CaptureUploader({ onArquivo, desabilitado = false, maxMB = 12 }: CaptureUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [qualidade, setQualidade] = useState<QualityReport | null>(null);
  const [verificando, setVerificando] = useState(false);
  const [sobre, setSobre] = useState(false);

  // libera o object URL anterior — sem isto, cada nova foto vaza memória
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const processar = useCallback(
    async (file: File) => {
      setErro(null);
      setQualidade(null);

      if (!ACEITOS.includes(file.type)) {
        setErro('Formato não suportado. Use JPEG, PNG ou WebP.');
        return;
      }
      if (file.size > maxMB * 1024 * 1024) {
        setErro(`Imagem acima de ${maxMB} MB. Reduza a resolução antes de enviar.`);
        return;
      }

      const url = URL.createObjectURL(file);
      setPreview((anterior) => {
        if (anterior) URL.revokeObjectURL(anterior);
        return url;
      });

      setVerificando(true);
      let rep: QualityReport | null = null;
      try {
        rep = await api.qualityCheck(file);
        setQualidade(rep);
      } catch (e) {
        // a checagem é um extra: se falhar, seguimos para a identificação
        if (e instanceof XiloScanError && e.status >= 500) setErro(null);
      } finally {
        setVerificando(false);
      }
      onArquivo(file, url, rep);
    },
    [maxMB, onArquivo],
  );

  return (
    <section className="xs-capture">
      <div
        className={`xs-capture__drop${sobre ? ' is-over' : ''}${desabilitado ? ' is-disabled' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setSobre(true); }}
        onDragLeave={() => setSobre(false)}
        onDrop={(e) => {
          e.preventDefault();
          setSobre(false);
          const f = e.dataTransfer.files[0];
          if (f && !desabilitado) void processar(f);
        }}
        onClick={() => !desabilitado && inputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !desabilitado) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={desabilitado ? -1 : 0}
        aria-label="Selecionar ou fotografar a face transversal da amostra"
      >
        {preview ? (
          <div className="xs-capture__previewWrap">
            <img className="xs-capture__preview" src={preview} alt="Pré-visualização da amostra" />
            <GuiaCentralizacao />
          </div>
        ) : (
          <div className="xs-capture__vazio">
            <GuiaCentralizacao vazio />
            <p className="xs-capture__titulo">Fotografe a face transversal (topo)</p>
            <p className="xs-capture__dica">
              Lixe a face, mantenha o corte perpendicular às fibras e enquadre
              dentro do quadrado. Luz difusa, sem flash direto.
            </p>
            <p className="xs-capture__dica xs-capture__dica--fraca">
              Arraste uma imagem, clique para escolher ou use a câmera · JPEG/PNG/WebP até {maxMB} MB
            </p>
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={ACEITOS.join(',')}
          capture="environment"
          hidden
          disabled={desabilitado}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void processar(f);
            e.target.value = '';
          }}
        />
      </div>

      {verificando && <p className="xs-msg xs-msg--info" role="status">Verificando a qualidade da imagem…</p>}
      {erro && <p className="xs-msg xs-msg--erro" role="alert">{erro}</p>}

      {qualidade && !qualidade.aceitavel && (
        <ul className="xs-msg xs-msg--aviso" aria-live="polite">
          {qualidade.avisos.map((a) => <li key={a}>{a}</li>)}
        </ul>
      )}
      {qualidade?.aceitavel && (
        <p className="xs-msg xs-msg--ok" role="status">
          Imagem adequada ({qualidade.largura}×{qualidade.altura} px, nitidez {qualidade.nitidez_laplaciana}).
        </p>
      )}
    </section>
  );
}

function GuiaCentralizacao({ vazio = false }: { vazio?: boolean }) {
  return (
    <svg className="xs-guia" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      {/* 85% = exatamente a região que o backend recorta */}
      <rect x="7.5" y="7.5" width="85" height="85" className="xs-guia__area" />
      {[['7.5', '7.5', '18', '7.5'], ['7.5', '7.5', '7.5', '18'],
        ['92.5', '7.5', '82', '7.5'], ['92.5', '7.5', '92.5', '18'],
        ['7.5', '92.5', '18', '92.5'], ['7.5', '92.5', '7.5', '82'],
        ['92.5', '92.5', '82', '92.5'], ['92.5', '92.5', '92.5', '82']].map((c, i) => (
        <line key={i} x1={c[0]} y1={c[1]} x2={c[2]} y2={c[3]} className="xs-guia__canto" />
      ))}
      <line x1="50" y1="44" x2="50" y2="56" className="xs-guia__mira" />
      <line x1="44" y1="50" x2="56" y2="50" className="xs-guia__mira" />
      {!vazio && (
        <g className="xs-guia__escala">
          <line x1="30" y1="96" x2="70" y2="96" />
          <line x1="30" y1="94" x2="30" y2="98" />
          <line x1="70" y1="94" x2="70" y2="98" />
          <text x="50" y="93" textAnchor="middle">≈ 2 cm</text>
        </g>
      )}
    </svg>
  );
}
