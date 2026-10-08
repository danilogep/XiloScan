/** Cliente HTTP do XiloScan. Sem dependências — fetch nativo + AbortController. */
import type {
  AuthResposta, ComparisonResult, HealthResponse, IdentifyOptions, LoginInput,
  QualityReport, RegistroInput, Taxonomy, WoodSpecies,
} from '../types/xiloscan';

function postJson<T>(caminho: string, corpo: unknown, signal?: AbortSignal): Promise<T> {
  return fetch(`${BASE}${caminho}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo),
    signal: signal ?? null,
  }).then(handle<T>);
}

const BASE = import.meta.env.VITE_API_URL ?? '/api';

export class XiloScanError extends Error {
  constructor(message: string, readonly status: number, readonly detalhe?: unknown) {
    super(message);
    this.name = 'XiloScanError';
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  let detalhe: unknown;
  let msg = `Erro ${res.status}`;
  try {
    detalhe = await res.json();
    const d = (detalhe as { detail?: unknown }).detail;
    if (typeof d === 'string') msg = d;
  } catch {
    /* resposta sem corpo JSON */
  }
  if (res.status === 413) msg = 'Imagem muito grande. Reduza a resolução e tente de novo.';
  if (res.status === 415) msg = 'Formato não suportado. Envie JPEG, PNG ou WebP.';
  if (res.status === 503) msg = 'Serviço indisponível: modelo ou índice não carregado.';
  throw new XiloScanError(msg, res.status, detalhe);
}

export const api = {
  health: (signal?: AbortSignal) =>
    fetch(`${BASE}/health`, { signal: signal ?? null }).then(handle<HealthResponse>),

  taxonomy: (signal?: AbortSignal) =>
    fetch(`${BASE}/taxonomy`, { signal: signal ?? null }).then(handle<Taxonomy>),

  species: (params: { offset?: number; limit?: number; q?: string } = {}, signal?: AbortSignal) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]),
    );
    return fetch(`${BASE}/species?${qs}`, { signal: signal ?? null }).then(
      handle<{ total: number; items: WoodSpecies[] }>,
    );
  },

  qualityCheck: (file: File, signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append('file', file);
    return fetch(`${BASE}/quality-check`, { method: 'POST', body: fd, signal: signal ?? null })
      .then(handle<QualityReport>);
  },

  identify: (file: File, options: IdentifyOptions = {}, signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('options', JSON.stringify(options));
    return fetch(`${BASE}/identify`, { method: 'POST', body: fd, signal: signal ?? null })
      .then(handle<ComparisonResult>);
  },

  /* cadastro / acesso */
  instituicoes: (signal?: AbortSignal) =>
    fetch(`${BASE}/auth/instituicoes`, { signal: signal ?? null }).then(handle<string[]>),

  registrar: (body: RegistroInput, signal?: AbortSignal) =>
    postJson<AuthResposta>('/auth/register', body, signal),

  entrar: (body: LoginInput, signal?: AbortSignal) =>
    postJson<AuthResposta>('/auth/login', body, signal),
};
