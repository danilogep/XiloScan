/** XiloScan — fluxo principal: capturar → informar atributos → identificar → comparar. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AttributeFilterPanel } from './components/AttributeFilterPanel';
import { CaptureUploader } from './components/CaptureUploader';
import { ConfidenceCard } from './components/ConfidenceCard';
import { SecaoSelector } from './components/SecaoSelector';
import { AuthGate } from './components/AuthGate';
import { Landing } from './components/Landing';
import { Sobre } from './components/Sobre';
import { api, XiloScanError } from './api/client';
import { useAuth } from './hooks/useAuth';
import { useTaxonomy } from './hooks/useTaxonomy';
import { contaAtributosInformados, TIPO_IMAGEM_LABEL } from './types/xiloscan';
import type {
  AnatomicalFeatures, ComparisonResult, HealthResponse, QualityReport, SecaoCorte,
} from './types/xiloscan';

export default function App() {
  const { sessao, usuario, entrar, sair } = useAuth();
  const { categorias, dicionario, erro: erroTax } = useTaxonomy();

  const [arquivo, setArquivo] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>('');
  const [qualidade, setQualidade] = useState<QualityReport | null>(null);
  const [secao, setSecao] = useState<SecaoCorte>('transversal');
  const [atributos, setAtributos] = useState<Partial<AnatomicalFeatures>>({});
  const [resultado, setResultado] = useState<ComparisonResult | null>(null);
  const [processando, setProcessando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [verAuth, setVerAuth] = useState(false);
  const [verSobre, setVerSobre] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    api.health(ac.signal).then(setHealth).catch(() => setHealth(null));
    return () => ac.abort();
  }, []);

  // cancela a requisição em voo se o componente sair
  useEffect(() => () => abortRef.current?.abort(), []);

  const onArquivo = useCallback((f: File, url: string, q: QualityReport | null) => {
    setArquivo(f);
    setPreviewUrl(url);
    setQualidade(q);
    setResultado(null);
    setErro(null);
  }, []);

  const identificar = useCallback(async () => {
    if (!arquivo) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setProcessando(true);
    setErro(null);
    try {
      const r = await api.identify(arquivo, { top_k: 3, atributos, secao }, ac.signal);
      setResultado({ ...r, imagem_usuario_url: previewUrl });
    } catch (e: unknown) {
      if (ac.signal.aborted) return;
      setErro(e instanceof XiloScanError ? e.message : 'Falha ao identificar a amostra.');
    } finally {
      if (!ac.signal.aborted) setProcessando(false);
    }
  }, [arquivo, atributos, previewUrl, secao]);

  const nInformados = contaAtributosInformados(atributos);
  const degradado = health?.status === 'degradado';

  // página Sobre/Ajuda/Créditos — acessível de qualquer lugar
  if (verSobre) return <Sobre onFechar={() => setVerSobre(false)} />;

  // abertura: landing → cadastro/login → app
  if (!sessao) {
    return verAuth
      ? <AuthGate onEntrar={entrar} onVoltar={() => setVerAuth(false)} />
      : <Landing onComecar={() => setVerAuth(true)} onSobre={() => setVerSobre(true)} />;
  }

  return (
    <div className="xs-app">
      <header className="xs-header">
        <div className="xs-header__topo">
          <div className="xs-marca">
            <img className="xs-marca__ic" src="/icon.svg" alt="" width="42" height="42" />
            <div>
              <h1 className="xs-marca__wm"><b>Xilo</b><i>Scan</i></h1>
              <span className="xs-marca__selo">ECAM · Produtos Florestais</span>
            </div>
          </div>
          {usuario && (
            <div className="xs-usuario">
              <span className="xs-usuario__info">
                {usuario.nome} · {usuario.instituicao === 'Outros' ? usuario.instituicao_outro : usuario.instituicao}
              </span>
              <button type="button" className="xs-btn--texto" onClick={sair}>Sair</button>
            </div>
          )}
        </div>
        <p>Identificação macroscópica de madeiras brasileiras · LPF/SFB · app Madeiras Comerciais do Brasil</p>
        {health && (
          <p className={`xs-header__status${degradado ? ' is-degradado' : ''}`}>
            {health.n_especies} espécies · {health.n_vetores} vetores · {health.backbone} · {health.device}
            {degradado && ' — serviço em modo degradado'}
          </p>
        )}
      </header>

      <main className="xs-main">
        <div className="xs-coluna">
          <CaptureUploader onArquivo={onArquivo} desabilitado={processando} />

          <p className="xs-msg xs-msg--info xs-foto-dica">
            <strong>A foto decide tudo.</strong> Dê zoom na sua foto: se você não distingue poros
            e anéis, a IA também não.{' '}
            <button type="button" className="xs-linklike" onClick={() => setVerSobre(true)}>
              Como tirar a foto boa
            </button>
          </p>

          <SecaoSelector valor={secao} onChange={setSecao} desabilitado={processando} />

          <AttributeFilterPanel
            categorias={categorias}
            valores={atributos}
            onChange={setAtributos}
            desabilitado={processando}
          />
          {erroTax && <p className="xs-msg xs-msg--erro">Taxonomia indisponível: {erroTax}</p>}

          <button
            type="button"
            className="xs-btn xs-btn--primario"
            disabled={!arquivo || processando}
            onClick={() => void identificar()}
          >
            {processando ? 'Analisando…' : `Identificar${nInformados ? ` (${nInformados} atributos)` : ''}`}
          </button>

          {qualidade && !qualidade.aceitavel && arquivo && (
            <p className="xs-msg xs-msg--aviso">
              A imagem tem problemas de qualidade. Você pode identificar assim mesmo,
              mas a confiança tende a cair.
            </p>
          )}
          {erro && <p className="xs-msg xs-msg--erro" role="alert">{erro}</p>}
        </div>

        <div className="xs-coluna xs-coluna--resultados">
          {!resultado && !processando && (
            <p className="xs-vazio">
              Os resultados aparecem aqui, ordenados por índice de confiança.
            </p>
          )}
          {processando && <p className="xs-vazio" role="status">Extraindo embedding e buscando no índice…</p>}

          {resultado && (
            <>
              <div className="xs-resumo">
                <span>{resultado.matches.length} candidatas</span>
                {resultado.secao_consultada && (
                  <span>Seção: {TIPO_IMAGEM_LABEL[resultado.secao_consultada] ?? resultado.secao_consultada}</span>
                )}
                <span>{resultado.processado_em_ms} ms</span>
              </div>
              <p className="xs-aviso-legal">{resultado.aviso}</p>

              {resultado.matches.map((m, i) => (
                <ConfidenceCard
                  key={m.especie.id}
                  match={m}
                  posicao={i + 1}
                  imagemUsuarioUrl={resultado.imagem_usuario_url}
                  ambiguo={resultado.top1_ambiguo}
                  dicionario={dicionario}
                />
              ))}
            </>
          )}
        </div>
      </main>

      <footer className="xs-rodape">
        <p className="xs-rodape__linha">
          <span className="xs-beta">Beta · em fase de testes</span>
          <button type="button" className="xs-btn--texto" onClick={() => setVerSobre(true)}>
            Sobre · Como tirar a foto · Créditos
          </button>
        </p>
        <p>
          O XiloScan usa IA e <strong>pode cometer erros</strong>: o resultado é auxiliar e
          exige confirmação por profissional habilitado — não use isoladamente para fins legais.
        </p>
        <p>
          Dados e imagens: <a href="https://lpf.florestal.gov.br" target="_blank" rel="noopener noreferrer">
          Laboratório de Produtos Florestais — Serviço Florestal Brasileiro (LPF/SFB)</a>.
          Vocabulário anatômico: app <strong>Madeiras Comerciais do Brasil (MCB)</strong>.
          Uso auxiliar, citando a fonte.
        </p>
      </footer>
    </div>
  );
}
