/**
 * Porta de entrada do XiloScan: cadastro simples (self-service, sem aprovação)
 * ou login. Captura a INSTITUIÇÃO de origem — "Outros" exige especificar.
 */
import { useEffect, useState, type FormEvent } from 'react';
import { api, XiloScanError } from '../api/client';
import { useInstallPrompt } from '../hooks/useInstallPrompt';
import type { AuthResposta } from '../types/xiloscan';

type Modo = 'registrar' | 'entrar';

export interface AuthGateProps {
  onEntrar: (r: AuthResposta) => void;
  onVoltar?: () => void;
}

export function AuthGate({ onEntrar, onVoltar }: AuthGateProps) {
  const [modo, setModo] = useState<Modo>('registrar');
  const [instituicoes, setInstituicoes] = useState<string[]>([]);
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [instituicao, setInstituicao] = useState('');
  const [instituicaoOutro, setInstituicaoOutro] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const { podeInstalar, instalar, ehIOS, instalado } = useInstallPrompt();

  useEffect(() => {
    const ac = new AbortController();
    api.instituicoes(ac.signal).then(setInstituicoes).catch(() => setInstituicoes([]));
    return () => ac.abort();
  }, []);

  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      const r = modo === 'registrar'
        ? await api.registrar({ nome, email, senha, instituicao, instituicao_outro: instituicaoOutro })
        : await api.entrar({ email, senha });
      onEntrar(r);
    } catch (err: unknown) {
      setErro(err instanceof XiloScanError ? err.message : 'Não foi possível concluir. Tente de novo.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="xs-auth">
      <div className="xs-auth__cartao">
        <div className="xs-auth__marca">
          <img src="/icon.svg" alt="" width="52" height="52" />
          <div>
            <h1 className="xs-auth__nome">XiloScan</h1>
            <p className="xs-auth__selo">ECAM · Produtos Florestais</p>
          </div>
        </div>
        <p className="xs-auth__sub">
          Identificação macroscópica de madeiras. Faça um cadastro rápido para usar —
          é liberado na hora.
        </p>

        <div className="xs-aviso-beta" role="note">
          <strong>Beta · em fase de testes.</strong> O XiloScan usa IA e <strong>pode cometer
          erros</strong> — o resultado é auxiliar e não substitui um profissional habilitado.
        </div>

        <div className="xs-auth__abas" role="tablist">
          <button
            type="button" role="tab" aria-selected={modo === 'registrar'}
            className={`xs-auth__aba${modo === 'registrar' ? ' is-ativa' : ''}`}
            onClick={() => { setModo('registrar'); setErro(null); }}
          >
            Criar cadastro
          </button>
          <button
            type="button" role="tab" aria-selected={modo === 'entrar'}
            className={`xs-auth__aba${modo === 'entrar' ? ' is-ativa' : ''}`}
            onClick={() => { setModo('entrar'); setErro(null); }}
          >
            Já tenho cadastro
          </button>
        </div>

        <form className="xs-auth__form" onSubmit={submeter}>
          {modo === 'registrar' && (
            <label className="xs-campo">
              <span>Nome</span>
              <input value={nome} onChange={(e) => setNome(e.target.value)} required minLength={2} autoComplete="name" />
            </label>
          )}

          <label className="xs-campo">
            <span>E-mail</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>

          <label className="xs-campo">
            <span>Senha</span>
            <input
              type="password" value={senha} onChange={(e) => setSenha(e.target.value)}
              required minLength={6} autoComplete={modo === 'registrar' ? 'new-password' : 'current-password'}
            />
          </label>

          {modo === 'registrar' && (
            <>
              <label className="xs-campo">
                <span>Instituição</span>
                <select value={instituicao} onChange={(e) => setInstituicao(e.target.value)} required>
                  <option value="" disabled>Selecione…</option>
                  {instituicoes.map((i) => <option key={i} value={i}>{i}</option>)}
                </select>
              </label>
              {instituicao === 'Outros' && (
                <label className="xs-campo">
                  <span>Qual instituição?</span>
                  <input
                    value={instituicaoOutro}
                    onChange={(e) => setInstituicaoOutro(e.target.value)}
                    required placeholder="Especifique"
                  />
                </label>
              )}
            </>
          )}

          {erro && <p className="xs-msg xs-msg--erro" role="alert">{erro}</p>}

          <button type="submit" className="xs-btn xs-btn--primario" disabled={enviando}>
            {enviando ? 'Enviando…' : modo === 'registrar' ? 'Criar cadastro e entrar' : 'Entrar'}
          </button>
        </form>

        <div className="xs-instalar">
          <h3 className="xs-instalar__t">📲 Instale na tela inicial</h3>

          {instalado ? (
            <p className="xs-instalar__ok">✓ App instalado. Abra pelo ícone na tela inicial.</p>
          ) : (
            <>
              {podeInstalar && (
                <button type="button" className="xs-btn xs-btn--ouro xs-instalar__btn" onClick={() => void instalar()}>
                  Instalar automaticamente
                </button>
              )}
              <p className="xs-instalar__ou">{podeInstalar ? 'ou faça você mesmo:' : 'faça você mesmo:'}</p>
              <p className="xs-instalar__p"><strong>iPhone (Safari):</strong> Compartilhar ↑ → “Adicionar à Tela de Início”.</p>
              <p className="xs-instalar__p"><strong>Android (Chrome):</strong> menu ⋮ → “Instalar aplicativo”.</p>
              <p className="xs-instalar__nota">
                {ehIOS
                  ? '⚠️ No iPhone/iPad não existe botão automático — use os passos do Safari acima.'
                  : '⚠️ O botão automático não funciona no iPhone/iPad — nesses, use os passos do Safari.'}
              </p>
            </>
          )}
        </div>

        {onVoltar && (
          <button type="button" className="xs-btn--texto xs-auth__voltar" onClick={onVoltar}>
            ← Voltar
          </button>
        )}

        <p className="xs-auth__rodape">
          Uso auxiliar. A identificação macroscópica exige confirmação por profissional habilitado.
        </p>
      </div>
    </div>
  );
}
