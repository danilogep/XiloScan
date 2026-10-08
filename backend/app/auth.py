"""
Cadastro simples e self-service do XiloScan (sem aprovação do programador).

Guarda nome, e-mail, senha (hash) e a INSTITUIÇÃO de origem do usuário
(PRF, PC, PM, IBAMA, ICMBio, IMEA…; "Outros" exige especificar). Pensado para
rodar no Railway com Postgres (variável DATABASE_URL); cai em SQLite localmente.

Sem dependências de criptografia externas: hashing com pbkdf2 (hashlib) e token
de sessão assinado com HMAC (stdlib). Precisa apenas de SQLAlchemy — e, no
Railway, do driver psycopg (postgres).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ─────────────────────────────────────────────────────────────── configuração

INSTITUICOES = [
    "PRF", "PF", "PC", "PM", "PMA",
    "IBAMA", "ICMBio", "IEF", "IMEA",
    "Serviço Florestal Brasileiro", "Secretaria de Meio Ambiente",
    "Ministério Público", "Universidade / Pesquisa", "Outros",
]

_SEGREDO = os.getenv("XILOSCAN_AUTH_SECRET", "dev-inseguro-troque-no-railway").encode()
_TOKEN_TTL = int(os.getenv("XILOSCAN_TOKEN_TTL", str(60 * 60 * 24 * 30)))  # 30 dias
_PBKDF2_ITER = 200_000


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./xiloscan_users.db")
    # o Railway entrega "postgres://…"; o SQLAlchemy 2 quer o driver explícito
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_engine = create_engine(_database_url(), pool_pre_ping=True, future=True)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    instituicao: Mapped[str] = mapped_column(String(80))
    instituicao_outro: Mapped[str] = mapped_column(String(160), default="")
    criado_em: Mapped[str] = mapped_column(String(40), default=lambda: datetime.now(UTC).isoformat())


def init_db() -> None:
    Base.metadata.create_all(_engine)


# ─────────────────────────────────────────────────────────────── senha / token

def hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _PBKDF2_ITER)
    return f"pbkdf2_sha256${_PBKDF2_ITER}${_b64(salt)}${_b64(dk)}"


def verifica_senha(senha: str, guardado: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = guardado.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), _unb64(salt_b64), int(iters))
        return hmac.compare_digest(dk, _unb64(dk_b64))
    except Exception:  # noqa: BLE001
        return False


def cria_token(user_id: int) -> str:
    corpo = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + _TOKEN_TTL}).encode())
    assinatura = _b64(hmac.new(_SEGREDO, corpo.encode(), hashlib.sha256).digest())
    return f"{corpo}.{assinatura}"


def le_token(token: str) -> int | None:
    try:
        corpo, assinatura = token.split(".")
        esperado = _b64(hmac.new(_SEGREDO, corpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(assinatura, esperado):
            return None
        dados = json.loads(_unb64(corpo))
        if int(dados["exp"]) < int(time.time()):
            return None
        return int(dados["sub"])
    except Exception:  # noqa: BLE001
        return None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ─────────────────────────────────────────────────────────────────── contratos

class RegistroIn(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    email: str = Field(max_length=200)
    senha: str = Field(min_length=6, max_length=128)
    instituicao: str
    instituicao_outro: str = ""

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("E-mail inválido.")
        return v


class LoginIn(BaseModel):
    email: str
    senha: str

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: str
    instituicao: str
    instituicao_outro: str = ""


class TokenOut(BaseModel):
    token: str
    usuario: UsuarioOut


# ─────────────────────────────────────────────────────────────────────── rotas

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_out(u: Usuario) -> UsuarioOut:
    return UsuarioOut(
        id=u.id, nome=u.nome, email=u.email,
        instituicao=u.instituicao, instituicao_outro=u.instituicao_outro,
    )


def _valida_instituicao(inst: str, outro: str) -> str:
    if inst not in INSTITUICOES:
        raise HTTPException(422, "Instituição inválida.")
    if inst == "Outros" and not outro.strip():
        raise HTTPException(422, "Especifique a instituição em 'Outros'.")
    return outro.strip() if inst == "Outros" else ""


@router.get("/instituicoes")
def instituicoes() -> list[str]:
    return INSTITUICOES


@router.post("/register", response_model=TokenOut)
def register(dados: RegistroIn) -> TokenOut:
    outro = _valida_instituicao(dados.instituicao, dados.instituicao_outro)
    with Session(_engine) as s:
        existe = s.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))
        if existe:
            raise HTTPException(409, "Já existe um cadastro com este e-mail.")
        u = Usuario(
            nome=dados.nome.strip(),
            email=dados.email.lower(),
            senha_hash=hash_senha(dados.senha),
            instituicao=dados.instituicao,
            instituicao_outro=outro,
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        return TokenOut(token=cria_token(u.id), usuario=_to_out(u))


@router.post("/login", response_model=TokenOut)
def login(dados: LoginIn) -> TokenOut:
    with Session(_engine) as s:
        u = s.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))
        if u is None or not verifica_senha(dados.senha, u.senha_hash):
            raise HTTPException(401, "E-mail ou senha incorretos.")
        return TokenOut(token=cria_token(u.id), usuario=_to_out(u))


def usuario_atual(authorization: str = Header(default="")) -> UsuarioOut:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Não autenticado.")
    uid = le_token(authorization[7:])
    if uid is None:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with Session(_engine) as s:
        u = s.get(Usuario, uid)
        if u is None:
            raise HTTPException(401, "Usuário não encontrado.")
        return _to_out(u)


@router.get("/me", response_model=UsuarioOut)
def me(atual: UsuarioOut = Depends(usuario_atual)) -> UsuarioOut:
    return atual
