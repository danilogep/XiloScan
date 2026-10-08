/** Sessão do usuário, persistida em localStorage (cadastro simples do XiloScan). */
import { useCallback, useState } from 'react';
import type { AuthResposta } from '../types/xiloscan';

const CHAVE = 'xiloscan_auth';

function ler(): AuthResposta | null {
  try {
    const raw = localStorage.getItem(CHAVE);
    return raw ? (JSON.parse(raw) as AuthResposta) : null;
  } catch {
    return null;
  }
}

export function useAuth() {
  const [sessao, setSessao] = useState<AuthResposta | null>(ler);

  const entrar = useCallback((r: AuthResposta) => {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(r));
    } catch {
      /* navegação privada / storage bloqueado: sessão vale só nesta aba */
    }
    setSessao(r);
  }, []);

  const sair = useCallback(() => {
    try {
      localStorage.removeItem(CHAVE);
    } catch {
      /* ignore */
    }
    setSessao(null);
  }, []);

  return { sessao, usuario: sessao?.usuario ?? null, entrar, sair };
}
