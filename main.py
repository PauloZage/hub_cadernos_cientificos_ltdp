# ============================================================================
# HUB DE CADERNOS CIENTÍFICOS — LTDP (Lubango, Huíla, Angola)
# Backend API — FastAPI + SQLAlchemy (SQLite por omissão, PostgreSQL via env)
# Fuso horário oficial: WAT — West Africa Time (UTC+1) / Africa/Luanda
# ----------------------------------------------------------------------------
# Execução:
#   pip install -r requirements.txt
#   uvicorn main:app --host 0.0.0.0 --port 8000
# Documentação interactiva: http://localhost:8000/docs
# ============================================================================

import hashlib
import hmac
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import (Column, ForeignKey, Integer, String, Text,
                        create_engine, func)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ----------------------------------------------------------------------------
# Configuração e contexto local
# ----------------------------------------------------------------------------
LOCALIZACAO = "LTDP - Lubango, Huíla, Angola"
FUSO_LABEL = "WAT (UTC+1)"
WAT = timezone(timedelta(hours=1), name="WAT")

# Render injecta DATABASE_URL automaticamente quando há um Postgres ligado ao serviço
DATABASE_URL = os.getenv("LTDP_DATABASE_URL") or os.getenv("DATABASE_URL") or "sqlite:///./ltdp_hub.db"
if DATABASE_URL.startswith("postgres://"):  # SQLAlchemy 2.x exige o prefixo completo
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
JWT_SECRET = os.getenv("LTDP_JWT_SECRET", "ALTERAR-EM-PRODUCAO-lubango-huila")
JWT_ALG = "HS256"
JWT_EXPIRA_HORAS = 12  # sessões longas: reduz re-autenticações em redes instáveis

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def agora_wat() -> datetime:
    return datetime.now(WAT)


# ----------------------------------------------------------------------------
# Modelos ORM
# ----------------------------------------------------------------------------
class Utilizador(Base):
    __tablename__ = "utilizadores"
    id_utilizador = Column(String, primary_key=True)
    nome_completo = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    perfil = Column(String, nullable=False, default="INVESTIGADOR")
    senha_hash = Column(String, nullable=False)
    activo = Column(Integer, nullable=False, default=1)
    criado_em = Column(String, nullable=False)


class Caderno(Base):
    __tablename__ = "cadernos"
    id_caderno = Column(String, primary_key=True)
    codigo_ltdp = Column(String, unique=True, nullable=False)
    titulo_invencao = Column(String, nullable=False)
    investigador_principal = Column(String, nullable=False)
    area_tecnologica = Column(String, nullable=False)
    data_inicio = Column(String, nullable=False)
    status_trl = Column(Integer, nullable=False, default=1)
    codigo_patente_previsto = Column(String, nullable=True)
    estado = Column(String, nullable=False, default="ACTIVO")
    localizacao = Column(String, nullable=False, default=LOCALIZACAO)
    fuso_horario = Column(String, nullable=False, default=FUSO_LABEL)
    criado_em = Column(String, nullable=False)
    actualizado_em = Column(String, nullable=False)


class EntradaCientifica(Base):
    __tablename__ = "entradas_cientificas"
    id_entrada = Column(String, primary_key=True)
    id_caderno = Column(String, ForeignKey("cadernos.id_caderno"), nullable=False)
    data_registo = Column(String, nullable=False)
    metodologia = Column(Text, nullable=False)
    resultados_brutos = Column(Text, nullable=False)
    link_repositorio_codigo = Column(String, nullable=True)
    hash_seguranca = Column(String, unique=True, nullable=False)
    hash_anterior = Column(String, nullable=True)
    assinatura_digital_investigador = Column(String, nullable=False)
    assinatura_testemunha = Column(String, nullable=True)
    origem_registo = Column(String, nullable=False, default="API")
    localizacao = Column(String, nullable=False, default=LOCALIZACAO)
    fuso_horario = Column(String, nullable=False, default=FUSO_LABEL)
    entrada_corrigida = Column(String, nullable=True)
    criado_em = Column(String, nullable=False)


Base.metadata.create_all(engine)

# ----------------------------------------------------------------------------
# Integridade intelectual: SHA-256 canónico e assinaturas
# ----------------------------------------------------------------------------
def calcular_hash_entrada(id_caderno: str, data_registo: str, metodologia: str,
                          resultados_brutos: str, link_repo: Optional[str]) -> str:
    """
    Hash canónico da entrada. A MESMA fórmula é usada pelo script de
    sincronização Excel — qualquer divergência indica adulteração dos dados.
    """
    payload = json.dumps(
        {
            "id_caderno": id_caderno,
            "data_registo": data_registo,
            "metodologia": metodologia.strip(),
            "resultados_brutos": resultados_brutos.strip(),
            "link_repositorio_codigo": (link_repo or "").strip(),
            "contexto": LOCALIZACAO,
        },
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assinar(email: str, hash_seguranca: str) -> str:
    """Assinatura digital leve: HMAC-SHA256(segredo do servidor, email + hash)."""
    msg = f"{email}|{hash_seguranca}".encode("utf-8")
    return hmac.new(JWT_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def hash_senha(senha: str, salt: Optional[str] = None) -> str:
    salt = salt or uuid.uuid4().hex
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 120_000)
    return f"{salt}${dk.hex()}"


def verificar_senha(senha: str, guardado: str) -> bool:
    salt, _ = guardado.split("$", 1)
    return hmac.compare_digest(hash_senha(senha, salt), guardado)


# ----------------------------------------------------------------------------
# Autenticação JWT (leve, sem dependências pesadas)
# ----------------------------------------------------------------------------
oauth2 = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utilizador_actual(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> Utilizador:
    erro = HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciais inválidas ou sessão expirada.")
    try:
        dados = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise erro
    u = db.get(Utilizador, dados.get("sub", ""))
    if not u or not u.activo:
        raise erro
    return u


def exigir_diretor(u: Utilizador = Depends(utilizador_actual)) -> Utilizador:
    if u.perfil != "DIRETOR":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso reservado ao Diretor do LTDP.")
    return u


# ----------------------------------------------------------------------------
# Schemas Pydantic
# ----------------------------------------------------------------------------
class CadernoIn(BaseModel):
    titulo_invencao: str
    investigador_principal: str
    area_tecnologica: str
    data_inicio: str = Field(..., description="YYYY-MM-DD")
    status_trl: int = Field(1, ge=1, le=9)
    codigo_patente_previsto: Optional[str] = None
    id_caderno: Optional[str] = Field(None, description="UUID gerado offline (sync Excel). Se omitido, o Hub gera.")


class EntradaIn(BaseModel):
    data_registo: Optional[str] = Field(None, description="ISO 8601; se omitido, usa agora em WAT.")
    metodologia: str
    resultados_brutos: str
    link_repositorio_codigo: Optional[str] = None
    assinatura_testemunha_email: Optional[str] = None
    id_entrada: Optional[str] = Field(None, description="UUID gerado offline (sync Excel) → idempotência.")
    origem_registo: str = Field("API", pattern="^(API|EXCEL_SYNC)$")


class UtilizadorIn(BaseModel):
    nome_completo: str
    email: str
    senha: str
    perfil: str = Field("INVESTIGADOR", pattern="^(DIRETOR|INVESTIGADOR|TESTEMUNHA)$")


# ----------------------------------------------------------------------------
# Aplicação
# ----------------------------------------------------------------------------
app = FastAPI(
    title="Hub de Cadernos Científicos — LTDP",
    description=f"Ecossistema de Cadernos de Laboratório Electrónicos (ELN). {LOCALIZACAO} — {FUSO_LABEL}.",
    version="1.1.0",
)

# CORS: permite que o script de sincronização e futuras apps acedam de outras origens
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("LTDP_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"],
)

PASTA_RAIZ = os.path.dirname(os.path.abspath(__file__))  # index.html vive ao lado de main.py


@app.on_event("startup")
def criar_diretor_inicial():
    """Cria o utilizador Diretor por omissão se a base estiver vazia."""
    db = SessionLocal()
    try:
        if db.query(Utilizador).count() == 0:
            db.add(Utilizador(
                id_utilizador=str(uuid.uuid4()),
                nome_completo="Diretor LTDP",
                email=os.getenv("LTDP_DIRETOR_EMAIL", "diretor@ltdp.ao"),
                perfil="DIRETOR",
                senha_hash=hash_senha(os.getenv("LTDP_DIRETOR_SENHA", "ltdp2026")),
                criado_em=agora_wat().isoformat(),
            ))
            db.commit()
    finally:
        db.close()


@app.get("/", tags=["Sistema"], include_in_schema=False)
def interface_web():
    """Serve a interface web do Hub (login, painel do Diretor, cadernos)."""
    return FileResponse(os.path.join(PASTA_RAIZ, "index.html"))


@app.get("/health", tags=["Sistema"])
def estado_sistema():
    return {"sistema": "Hub de Cadernos Científicos — LTDP", "localizacao": LOCALIZACAO,
            "fuso_horario": FUSO_LABEL, "hora_local": agora_wat().isoformat(), "estado": "online"}


# ---------------------------- Autenticação ---------------------------------
@app.post("/auth/login", tags=["Autenticação"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(Utilizador).filter(Utilizador.email == form.username).first()
    if not u or not verificar_senha(form.password, u.senha_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou senha incorrectos.")
    token = jwt.encode(
        {"sub": u.id_utilizador, "perfil": u.perfil,
         "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRA_HORAS)},
        JWT_SECRET, algorithm=JWT_ALG,
    )
    return {"access_token": token, "token_type": "bearer", "perfil": u.perfil,
            "expira_em_horas": JWT_EXPIRA_HORAS}


@app.post("/auth/utilizadores", tags=["Autenticação"], status_code=201)
def criar_utilizador(dados: UtilizadorIn, db: Session = Depends(get_db),
                     _: Utilizador = Depends(exigir_diretor)):
    if db.query(Utilizador).filter(Utilizador.email == dados.email).first():
        raise HTTPException(409, "Já existe um utilizador com este email.")
    u = Utilizador(id_utilizador=str(uuid.uuid4()), nome_completo=dados.nome_completo,
                   email=dados.email, perfil=dados.perfil,
                   senha_hash=hash_senha(dados.senha), criado_em=agora_wat().isoformat())
    db.add(u); db.commit()
    return {"id_utilizador": u.id_utilizador, "email": u.email, "perfil": u.perfil}


# ------------------------------ Cadernos ------------------------------------
@app.post("/cadernos", tags=["Cadernos"], status_code=201)
def abrir_caderno(dados: CadernoIn, db: Session = Depends(get_db),
                  u: Utilizador = Depends(utilizador_actual)):
    """Abre um novo caderno de invenção no Hub."""
    cid = dados.id_caderno or str(uuid.uuid4())
    if db.get(Caderno, cid):
        raise HTTPException(409, "Caderno já existe no Hub (sincronização idempotente).")
    ano = agora_wat().year
    seq = db.query(func.count(Caderno.id_caderno)).scalar() + 1
    agora = agora_wat().isoformat()
    c = Caderno(
        id_caderno=cid, codigo_ltdp=f"LTDP/CAD/{ano}/{seq:04d}",
        titulo_invencao=dados.titulo_invencao,
        investigador_principal=dados.investigador_principal,
        area_tecnologica=dados.area_tecnologica, data_inicio=dados.data_inicio,
        status_trl=dados.status_trl, codigo_patente_previsto=dados.codigo_patente_previsto,
        criado_em=agora, actualizado_em=agora,
    )
    db.add(c); db.commit()
    return {"id_caderno": c.id_caderno, "codigo_ltdp": c.codigo_ltdp,
            "mensagem": f"Caderno aberto no {LOCALIZACAO}.", "registado_por": u.email}


@app.get("/cadernos", tags=["Cadernos"])
def listar_cadernos(area: Optional[str] = Query(None), trl_min: Optional[int] = Query(None, ge=1, le=9),
                    estado: Optional[str] = Query(None), db: Session = Depends(get_db),
                    _: Utilizador = Depends(utilizador_actual)):
    """Painel do Diretor: lista todos os projectos e o estado de desenvolvimento (TRL)."""
    q = db.query(Caderno)
    if area:
        q = q.filter(Caderno.area_tecnologica.ilike(f"%{area}%"))
    if trl_min:
        q = q.filter(Caderno.status_trl >= trl_min)
    if estado:
        q = q.filter(Caderno.estado == estado.upper())
    cadernos = q.order_by(Caderno.status_trl.desc()).all()
    resposta = []
    for c in cadernos:
        n = db.query(func.count(EntradaCientifica.id_entrada)).filter(
            EntradaCientifica.id_caderno == c.id_caderno).scalar()
        ultima = db.query(func.max(EntradaCientifica.data_registo)).filter(
            EntradaCientifica.id_caderno == c.id_caderno).scalar()
        resposta.append({
            "id_caderno": c.id_caderno, "codigo_ltdp": c.codigo_ltdp,
            "titulo_invencao": c.titulo_invencao,
            "investigador_principal": c.investigador_principal,
            "area_tecnologica": c.area_tecnologica, "data_inicio": c.data_inicio,
            "status_trl": c.status_trl, "trl_descricao": f"TRL {c.status_trl}/9",
            "codigo_patente_previsto": c.codigo_patente_previsto, "estado": c.estado,
            "total_entradas": n, "ultima_actividade": ultima,
        })
    return {"localizacao": LOCALIZACAO, "total": len(resposta), "cadernos": resposta}


@app.get("/cadernos/{id_caderno}/entradas", tags=["Entradas Científicas"])
def listar_entradas(id_caderno: str, db: Session = Depends(get_db),
                    _: Utilizador = Depends(utilizador_actual)):
    if not db.get(Caderno, id_caderno):
        raise HTTPException(404, "Caderno não encontrado.")
    entradas = (db.query(EntradaCientifica)
                .filter(EntradaCientifica.id_caderno == id_caderno)
                .order_by(EntradaCientifica.data_registo).all())
    return [{
        "id_entrada": e.id_entrada, "data_registo": e.data_registo,
        "metodologia": e.metodologia, "resultados_brutos": e.resultados_brutos,
        "link_repositorio_codigo": e.link_repositorio_codigo,
        "hash_seguranca": e.hash_seguranca, "hash_anterior": e.hash_anterior,
        "assinatura_digital_investigador": e.assinatura_digital_investigador,
        "assinatura_testemunha": e.assinatura_testemunha,
        "origem_registo": e.origem_registo,
    } for e in entradas]


@app.post("/cadernos/{id_caderno}/entradas", tags=["Entradas Científicas"], status_code=201)
def adicionar_entrada(id_caderno: str, dados: EntradaIn, db: Session = Depends(get_db),
                      u: Utilizador = Depends(utilizador_actual)):
    """
    Regista um dia de progresso científico. O Hub:
    1. Gera o SHA-256 canónico do conteúdo (integridade intelectual);
    2. Encadeia com o hash da entrada anterior (cadeia de auditoria);
    3. Assina digitalmente em nome do investigador autenticado.
    Idempotente: se o id_entrada (UUID offline) já existir, devolve 409 sem duplicar.
    """
    if not db.get(Caderno, id_caderno):
        raise HTTPException(404, "Caderno não encontrado.")
    eid = dados.id_entrada or str(uuid.uuid4())
    if db.get(EntradaCientifica, eid):
        raise HTTPException(409, "Entrada já sincronizada no Hub (sem duplicação).")

    data_registo = dados.data_registo or agora_wat().isoformat()
    h = calcular_hash_entrada(id_caderno, data_registo, dados.metodologia,
                              dados.resultados_brutos, dados.link_repositorio_codigo)
    if db.query(EntradaCientifica).filter(EntradaCientifica.hash_seguranca == h).first():
        raise HTTPException(409, "Conteúdo idêntico já registado (hash duplicado).")

    anterior = (db.query(EntradaCientifica)
                .filter(EntradaCientifica.id_caderno == id_caderno)
                .order_by(EntradaCientifica.criado_em.desc()).first())

    e = EntradaCientifica(
        id_entrada=eid, id_caderno=id_caderno, data_registo=data_registo,
        metodologia=dados.metodologia, resultados_brutos=dados.resultados_brutos,
        link_repositorio_codigo=dados.link_repositorio_codigo,
        hash_seguranca=h, hash_anterior=anterior.hash_seguranca if anterior else None,
        assinatura_digital_investigador=assinar(u.email, h),
        assinatura_testemunha=(assinar(dados.assinatura_testemunha_email, h)
                               if dados.assinatura_testemunha_email else None),
        origem_registo=dados.origem_registo, criado_em=agora_wat().isoformat(),
    )
    caderno = db.get(Caderno, id_caderno)
    caderno.actualizado_em = agora_wat().isoformat()
    db.add(e); db.commit()
    return {"id_entrada": e.id_entrada, "hash_seguranca": e.hash_seguranca,
            "hash_anterior": e.hash_anterior,
            "assinatura_digital_investigador": e.assinatura_digital_investigador,
            "localizacao": LOCALIZACAO, "fuso_horario": FUSO_LABEL}


@app.get("/entradas/{id_entrada}/verificar", tags=["Auditoria"])
def verificar_integridade(id_entrada: str, db: Session = Depends(get_db),
                          _: Utilizador = Depends(utilizador_actual)):
    """Recalcula o SHA-256 e compara com o registado — prova de não-adulteração."""
    e = db.get(EntradaCientifica, id_entrada)
    if not e:
        raise HTTPException(404, "Entrada não encontrada.")
    recalculado = calcular_hash_entrada(e.id_caderno, e.data_registo, e.metodologia,
                                        e.resultados_brutos, e.link_repositorio_codigo)
    integra = hmac.compare_digest(recalculado, e.hash_seguranca)
    return {"id_entrada": id_entrada, "hash_registado": e.hash_seguranca,
            "hash_recalculado": recalculado, "integridade": "ÍNTEGRA" if integra else "⚠ QUEBRA DE INTEGRIDADE",
            "verificado_em": agora_wat().isoformat()}


# --------------------------- Exportação Excel -------------------------------
@app.get("/cadernos/export/excel", tags=["Exportação"])
def exportar_excel(db: Session = Depends(get_db), _: Utilizador = Depends(exigir_diretor)):
    """Dump completo formatado (.xlsx) para arquivo/relatório do Diretor."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    azul = PatternFill("solid", start_color="1F4E79")
    cab = Font(bold=True, color="FFFFFF", name="Arial")

    ws1 = wb.active
    ws1.title = "Cadernos"
    cols1 = ["ID_Caderno", "Código LTDP", "Título da Invenção", "Investigador Principal",
             "Área Tecnológica", "Data Início", "Status TRL", "Código Patente Previsto",
             "Estado", "Localização", "Fuso Horário"]
    ws1.append(cols1)
    for c in db.query(Caderno).all():
        ws1.append([c.id_caderno, c.codigo_ltdp, c.titulo_invencao, c.investigador_principal,
                    c.area_tecnologica, c.data_inicio, c.status_trl, c.codigo_patente_previsto,
                    c.estado, c.localizacao, c.fuso_horario])

    ws2 = wb.create_sheet("Entradas_Cientificas")
    cols2 = ["ID_Entrada", "ID_Caderno", "Data Registo", "Metodologia", "Resultados Brutos",
             "Link Repositório", "Hash SHA-256", "Hash Anterior", "Assinatura Investigador",
             "Assinatura Testemunha", "Origem"]
    ws2.append(cols2)
    for e in db.query(EntradaCientifica).order_by(EntradaCientifica.data_registo).all():
        ws2.append([e.id_entrada, e.id_caderno, e.data_registo, e.metodologia,
                    e.resultados_brutos, e.link_repositorio_codigo, e.hash_seguranca,
                    e.hash_anterior, e.assinatura_digital_investigador,
                    e.assinatura_testemunha, e.origem_registo])

    for ws, cols in ((ws1, cols1), (ws2, cols2)):
        for i, _c in enumerate(cols, 1):
            cel = ws.cell(row=1, column=i)
            cel.fill, cel.font = azul, cab
            cel.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cel.column_letter].width = 24
        ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nome = f"LTDP_Hub_Export_{agora_wat().strftime('%Y%m%d_%H%M')}_WAT.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
