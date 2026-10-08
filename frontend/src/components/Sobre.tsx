/**
 * Página "Sobre / Ajuda / Créditos" do XiloScan.
 * Reúne: aviso de fase de testes, aviso de IA, como tirar a foto (com a
 * importância da qualidade), como instalar na tela inicial, e os créditos/licença.
 */

export interface SobreProps {
  onFechar: () => void;
}

export function Sobre({ onFechar }: SobreProps) {
  return (
    <div className="xs-sobre">
      <div className="xs-sobre__inner">
        <header className="xs-sobre__topo">
          <div className="xs-lock">
            <img className="xs-lock__ic" src="/icon.svg" alt="" width="42" height="42" />
            <div>
              <span className="xs-lock__wm"><b>Xilo</b><i>Scan</i></span>
              <span className="xs-lock__selo">Sobre · Ajuda · Créditos</span>
            </div>
          </div>
          <button type="button" className="xs-btn--texto" onClick={onFechar}>Fechar ✕</button>
        </header>

        <div className="xs-aviso-beta" role="note">
          <strong>Versão em fase de testes (beta).</strong> Estamos ajustando o XiloScan com
          uso real — funcionalidades e resultados podem mudar. Seu feedback ajuda a melhorar.
        </div>

        <section className="xs-sobre__bloco">
          <h2>É uma IA — e pode errar</h2>
          <p>
            O XiloScan usa inteligência artificial para <em>sugerir</em> as espécies mais
            parecidas com a sua foto. Como toda IA, ele <strong>pode cometer erros</strong>.
            O resultado é <strong>auxiliar</strong> e não substitui a análise de um
            profissional habilitado. Use-o como ponto de partida, nunca como conclusão isolada.
          </p>
        </section>

        <section className="xs-sobre__bloco">
          <h2>Como tirar a foto (isto é o que mais importa)</h2>
          <p className="xs-sobre__chave">
            A qualidade da foto decide tudo. <strong>Teste do zoom:</strong> dê zoom na sua
            própria foto, no celular. Se <em>você</em> não distingue poros, anéis e o desenho
            da madeira, <strong>a IA também não vai</strong> — refaça a foto.
          </p>
          <ul className="xs-lista">
            <li>Fotografe a superfície <strong>cortada e lixada</strong> da madeira, bem de perto.</li>
            <li><strong>Foco e luz</strong> são tudo: luz difusa, sem sombra dura nem reflexo/brilho.</li>
            <li>Preencha o quadro com a madeira (use a guia da tela). Sem fundo, dedos ou régua no meio.</li>
            <li>Segure firme; se tremer, a imagem “borra” e perde os detalhes.</li>
            <li>Informe a <strong>seção certa</strong>: transversal = topo (anéis e poros); tangencial = face lateral.</li>
          </ul>
        </section>

        <section className="xs-sobre__bloco">
          <h2>Créditos e licença</h2>
          <p>
            <strong>Dados e imagens:</strong> Laboratório de Produtos Florestais — Serviço
            Florestal Brasileiro (<a href="https://lpf.florestal.gov.br" target="_blank" rel="noopener noreferrer">LPF/SFB</a>).
            Base de dados: Vera T. R. Coradin, José Arlete A. Camargos, Tereza Cristina M.
            Pastores e Alexandre Gabriel Christo <em>(in memoriam)</em>.
          </p>
          <p>
            <strong>Vocabulário anatômico:</strong> app <em>Madeiras Comerciais do Brasil</em>
            (MCB) — UFS/LAVD + SFB: Claudio Sergio Lisi, Christiano Santana, Nayanne Azevedo
            Menezes, Alexandre Bahia Gontijo e Vera T. R. Coradin.
          </p>
          <p className="xs-sobre__lic">
            Uso acadêmico e auxiliar, citando a fonte. A identificação macroscópica exige
            confirmação por profissional habilitado — não use isoladamente para fins legais.
          </p>
        </section>

        <div className="xs-sobre__rodape">
          <button type="button" className="xs-btn xs-btn--ouro" onClick={onFechar}>Voltar</button>
        </div>
      </div>
    </div>
  );
}
