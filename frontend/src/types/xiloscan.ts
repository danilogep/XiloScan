/**
 * Contratos do XiloScan — espelham backend/app/schemas.py 1:1.
 *
 * Os códigos anatômicos são literais em vez de `string` para que um valor
 * inválido quebre no `tsc`, e não em runtime na frente do usuário.
 * Fonte da verdade: data/mcb_taxonomy.json.
 */

/* ─────────────────────────────────────────────── vocabulário controlado MCB */

export const DOMINIOS = [
  'AMAZONIA', 'CAATINGA', 'CERRADO', 'MATA_ATLANTICA', 'PAMPA', 'PANTANAL',
] as const;
export type DominioFitogeografico = (typeof DOMINIOS)[number];

export const CORES = [
  'BRANCA_BEGE', 'AMARELA', 'ROSA_AVERMELHADA', 'MARROM_AMARELADA', 'MARROM_ESCURA',
] as const;
export type CorMadeira = (typeof CORES)[number];

export const ANEIS = ['DISTINTOS', 'POUCO_DISTINTOS', 'INDISTINTOS'] as const;
export type AneisCrescimento = (typeof ANEIS)[number];

export const VASOS_POROSIDADE = [
  'DIFUSA', 'ANEL_POROSO', 'SEMI_ANEL_POROSO', 'NAO_VISIVEIS',
] as const;
export type VasosPorosidade = (typeof VASOS_POROSIDADE)[number];

export const VASOS_AGRUPAMENTO = [
  'SOLITARIOS', 'MULTIPLOS_RADIAIS', 'CACHOS', 'NAO_VISIVEIS',
] as const;
export type VasosAgrupamento = (typeof VASOS_AGRUPAMENTO)[number];

export const VASOS_OBSTRUCAO = [
  'DESOBSTRUIDOS', 'OBSTRUIDOS_TILOS', 'OBSTRUIDOS_SUBST',
] as const;
export type VasosObstrucao = (typeof VASOS_OBSTRUCAO)[number];

export const TILOSES = [
  'AUSENTES', 'TILOS', 'SUBST_BRANCAS', 'SUBST_AMARELAS', 'SUBST_ESCURAS',
] as const;
export type TilosesSubstancias = (typeof TILOSES)[number];

export const PARENQUIMA_AXIAL = [
  'AUSENTE_INDISTINTO', 'APOTRAQUEAL', 'PARATRAQUEAL',
] as const;
export type ParenquimaAxial = (typeof PARENQUIMA_AXIAL)[number];

export const PARENQUIMA_APOTRAQUEAL = [
  'DIFUSO', 'DIFUSO_AGREGADOS', 'EM_LINHAS',
] as const;
export type ParenquimaApotraqueal = (typeof PARENQUIMA_APOTRAQUEAL)[number];

export const PARENQUIMA_PARATRAQUEAL = [
  'ESCASSO', 'VASICENTRICO', 'ALIFORME', 'ALIFORME_CONFLUENTE', 'EM_FAIXAS',
] as const;
export type ParenquimaParatraqueal = (typeof PARENQUIMA_PARATRAQUEAL)[number];

export const RAIOS = [
  'OLHO_NU_TOPO', 'SOB_LENTE', 'ESPELHADO_TANG', 'ESTRATIFICADOS', 'NAO_VISIVEIS',
] as const;
export type RaiosVisibilidade = (typeof RAIOS)[number];

/* ────────────────────────────────────────────────────────── entidades core */

export interface AnatomicalFeatures {
  dominio_fitogeografico: DominioFitogeografico[];
  cor_madeira: CorMadeira | null;
  aneis_crescimento: AneisCrescimento | null;
  vasos_porosidade: VasosPorosidade | null;
  vasos_agrupamento: VasosAgrupamento[];
  vasos_obstrucao: VasosObstrucao | null;
  tiloses_substancias: TilosesSubstancias[];
  parenquima_axial: ParenquimaAxial | null;
  parenquima_apotraqueal: ParenquimaApotraqueal[];
  parenquima_paratraqueal: ParenquimaParatraqueal[];
  raios_visibilidade: RaiosVisibilidade[];
}

/** Chave de qualquer campo anatômico — usada para indexar o formulário. */
export type AnatomicalField = keyof AnatomicalFeatures;

export interface Taxonomia {
  nome_cientifico: string;
  autor: string;
  familia: string;
  sinonimos: string[];
  nomes_populares: string[];
}

/** Seção da foto — só as vistas do lenho servem à comparação visual. */
export const SECOES_CORTE = ['transversal', 'tangencial', 'radial'] as const;
export type SecaoCorte = (typeof SECOES_CORTE)[number];

/** Uma foto da espécie, com a seção a que pertence. */
export interface ImagemRef {
  tipo: string; // transversal|tangencial|radial|arvore|tora|casca|madeira
  url: string;
  arquivo: string;
  fonte_url: string;
}

/** Rótulos legíveis de cada tipo de imagem, para a galeria. */
export const TIPO_IMAGEM_LABEL: Record<string, string> = {
  transversal: 'Seção transversal',
  tangencial: 'Corte tangencial',
  radial: 'Corte radial',
  arvore: 'Árvore',
  tora: 'Tora',
  casca: 'Casca',
  madeira: 'Madeira',
};

export interface WoodSpecies {
  id: string;
  lpf_id: number | null;
  fonte_url: string;
  taxonomia: Taxonomia;
  anatomia: AnatomicalFeatures;
  cor_descricao: string;
  gra: string;
  textura: string;
  densidade_basica: number | null;
  imagem_url: string | null;
  imagens: ImagemRef[];
  /** 0–1: fração dos descritores anatômicos preenchidos para esta espécie. */
  completeness: number;
}

export type NivelConfianca = 'alta' | 'media' | 'baixa';
export type FeatureStatus = 'coincidente' | 'divergente' | 'nao_informado';

export interface FeatureMatch {
  campo: AnatomicalField;
  rotulo: string;
  valor_usuario: string[];
  valor_especie: string[];
  status: FeatureStatus;
  peso: number;
}

export interface SpeciesMatch {
  especie: WoodSpecies;
  score_visual: number;
  score_atributos: number;
  score_final: number;
  confianca_pct: number;
  nivel: NivelConfianca;
  features: FeatureMatch[];
  imagem_referencia_url: string | null;
}

export interface ComparisonResult {
  request_id: string;
  imagem_usuario_url: string;
  processado_em_ms: number;
  secao_consultada: SecaoCorte | null;
  matches: SpeciesMatch[];
  /** Diferença < 0.05 entre 1º e 2º: exige confirmação humana. */
  top1_ambiguo: boolean;
  aviso: string;
}

/* ─────────────────────────────────────────────────────────── API auxiliar */

export interface IdentifyOptions {
  top_k?: number;
  peso_visual?: number;
  atributos?: Partial<AnatomicalFeatures>;
  secao?: SecaoCorte;
}

export interface QualityReport {
  largura: number;
  altura: number;
  nitidez_laplaciana: number;
  brilho_medio: number;
  pct_saturado: number;
  aceitavel: boolean;
  avisos: string[];
}

export interface TaxonomyOption {
  codigo: string;
  rotulo: string;
  confianca: 'confirmado' | 'inferido';
  hex_referencia?: string;
  nota?: string;
}

export interface TaxonomyCategory {
  chave: AnatomicalField;
  rotulo: string;
  cardinalidade_observada: number;
  multivalorado: boolean;
  peso_filtro_hibrido: number;
  depende_de?: { chave: AnatomicalField; valor: string };
  opcoes: TaxonomyOption[];
}

export interface Taxonomy {
  versao: string;
  categorias: TaxonomyCategory[];
}

export interface HealthResponse {
  status: 'ok' | 'degradado';
  modelo_carregado: boolean;
  indice_carregado: boolean;
  n_especies: number;
  n_vetores: number;
  device: string;
  backbone: string;
}

/* ─────────────────────────────────────────────────────────── cadastro/acesso */

export interface UsuarioAuth {
  id: number;
  nome: string;
  email: string;
  instituicao: string;
  instituicao_outro: string;
}

export interface AuthResposta {
  token: string;
  usuario: UsuarioAuth;
}

export interface RegistroInput {
  nome: string;
  email: string;
  senha: string;
  instituicao: string;
  instituicao_outro?: string;
}

export interface LoginInput {
  email: string;
  senha: string;
}

/* ───────────────────────────────────────────────────────────────── helpers */

export const EMPTY_FEATURES: AnatomicalFeatures = {
  dominio_fitogeografico: [],
  cor_madeira: null,
  aneis_crescimento: null,
  vasos_porosidade: null,
  vasos_agrupamento: [],
  vasos_obstrucao: null,
  tiloses_substancias: [],
  parenquima_axial: null,
  parenquima_apotraqueal: [],
  parenquima_paratraqueal: [],
  raios_visibilidade: [],
};

export function contaAtributosInformados(f: Partial<AnatomicalFeatures>): number {
  return Object.values(f).filter((v) => (Array.isArray(v) ? v.length > 0 : Boolean(v))).length;
}

export function nomeCompleto(t: Taxonomia): string {
  return t.autor ? `${t.nome_cientifico} ${t.autor}` : t.nome_cientifico;
}
