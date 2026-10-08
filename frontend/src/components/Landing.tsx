/**
 * Tela de abertura (landing) do XiloScan — apresenta o produto na marca
 * navy/ouro e leva ao cadastro. Sem citar órgãos: mensagem por benefício.
 */

export interface LandingProps {
  onComecar: () => void;
  onSobre: () => void;
}

const PASSOS = [
  { n: '1', t: 'Fotografe o corte', d: 'Aponte para a superfície da madeira — transversal ou tangencial.' },
  { n: '2', t: 'Escolha a seção', d: 'A comparação usa só imagens da mesma seção que você fotografou.' },
  { n: '3', t: 'Compare e conclua', d: 'Receba as espécies mais prováveis com o índice de confiança e as fotos de referência.' },
];

export function Landing({ onComecar, onSobre }: LandingProps) {
  return (
    <div className="xs-landing">
      <div className="xs-landing__inner">
        <header className="xs-landing__topo">
          <div className="xs-lock">
            <img className="xs-lock__ic" src="/icon.svg" alt="" width="46" height="46" />
            <div>
              <span className="xs-lock__wm"><b>Xilo</b><i>Scan</i></span>
              <span className="xs-lock__selo">ECAM · Produtos Florestais</span>
            </div>
          </div>
          <span className="xs-beta">Beta</span>
        </header>

        <section className="xs-landing__hero">
          <h1 className="xs-landing__head">A espécie da madeira, <em>na palma da mão.</em></h1>
          <p className="xs-landing__sub">
            Macroscopia assistida por IA. Fotografe o corte, escolha a seção e compare com o
            acervo — as espécies mais prováveis aparecem com o índice de confiança e as
            imagens de referência para você concluir.
          </p>
          <div className="xs-landing__cta">
            <button type="button" className="xs-btn xs-btn--ouro" onClick={onComecar}>Começar</button>
            <button type="button" className="xs-btn xs-btn--fantasma" onClick={onComecar}>Já tenho cadastro</button>
          </div>
          <p className="xs-landing__para">Para fiscalização, ensino e pesquisa em produtos florestais</p>
          <p className="xs-landing__ia">
            O XiloScan usa IA e pode cometer erros — resultado auxiliar.{' '}
            <button type="button" className="xs-linklike" onClick={onSobre}>Como tirar a boa foto →</button>
          </p>
        </section>

        <section className="xs-landing__passos" aria-label="Como funciona">
          {PASSOS.map((p) => (
            <div key={p.n} className="xs-passo">
              <span className="xs-passo__n">{p.n}</span>
              <h3 className="xs-passo__t">{p.t}</h3>
              <p className="xs-passo__d">{p.d}</p>
            </div>
          ))}
        </section>

        <footer className="xs-landing__rodape">
          <p className="xs-creditos">
            Dados e imagens: <strong>Laboratório de Produtos Florestais — Serviço Florestal
            Brasileiro (LPF/SFB)</strong>. Vocabulário anatômico: app <strong>Madeiras
            Comerciais do Brasil (MCB)</strong>. Uso auxiliar, citando a fonte.
          </p>
          <p className="xs-disclaimer">
            A identificação macroscópica exige confirmação por profissional habilitado — não
            use isoladamente para fins legais.
          </p>
        </footer>
      </div>
    </div>
  );
}
