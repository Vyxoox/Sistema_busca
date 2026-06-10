import os
import re
import shutil
import logging

from collections import Counter
from threading import Lock
from typing import Any
from urllib.parse import urlparse, urljoin
from datetime import datetime, date, UTC

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, or_, text
from whoosh.index import open_dir, create_in
from whoosh.query import Every
from time import perf_counter
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from core.authz import superadmin_required

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

from core.extensions import db, login_manager, csrf, limiter
from models import Usuario, Funcionario
from core.config import Config
from core.schema import schema
from core.logging_setup import setup_logging
from routes.auth import auth_bp
from routes.funcionarios import funcionarios_bp
from routes.busca import busca_bp
from routes.columns import columns_bp
from routes.reindexar import reindexar_bp
from routes.verfunc import verfunc_bp
from routes.planilha import planilha_bp
from routes.criacao import criacao_bp
from routes.editfunc import editfunc_bp
from routes.usuarios import usuario_bp
from routes.ouvidoria import ouvidoria_bp

from services.normalizacao_service import normalizar_cpf, normalizar_rg, normalizar_maiusculo, normalizar_titulo
from services.formatacao_service import formatar_rg, formatar_cpf
from services.auditoria_services import registrar_evento_seguro

from core.audit_policy import audit_event

app = Flask(__name__)
app.config.from_object(Config)
APP_START_TIME = datetime.now(UTC)

# Logging com rotação por categoria (aplicação/segurança/auditoria/erros)
setup_logging(app)
logging.getLogger("observabilidade").info("TESTE OBSERVABILIDADE")
logging.getLogger("auditoria").info("TESTE AUDITORIA")
logging.getLogger("seguranca").info("TESTE SEGURANCA")
logging.getLogger("erros").error("TESTE ERRO")
app.logger.info("TESTE APP LOGGER")

db.init_app(app)

login_manager.init_app(app)
csrf.init_app(app)

limiter.init_app(app)

login_manager.login_view = 'auth.login'
login_manager.login_message = 'É necessário fazer login para acessar esta página.'
login_manager.login_message_category = 'error'


@login_manager.unauthorized_handler
def tratar_nao_autenticado():
    registrar_evento_seguro(
        'AUTH_ACESSO_NAO_AUTENTICADO',
        categoria='seguranca',
        status='falha',
        recurso='autenticacao',
        detalhes={
            'endpoint': request.endpoint or '',
            'rota_solicitada': request.path,
        },
    )
    flash(login_manager.login_message, login_manager.login_message_category)
    destino = request.full_path if request.query_string else request.path
    return redirect(url_for('auth.login', next=destino))

app.register_blueprint(auth_bp)
app.register_blueprint(funcionarios_bp)
app.register_blueprint(busca_bp)
app.register_blueprint(columns_bp)
app.register_blueprint(reindexar_bp)
app.register_blueprint(verfunc_bp)

app.register_blueprint(planilha_bp)
app.register_blueprint(criacao_bp)
app.register_blueprint(editfunc_bp)
app.register_blueprint(usuario_bp)
app.register_blueprint(ouvidoria_bp)
EMAIL_SEDE_PADRAO = os.getenv('EMAIL_SEDE_PADRAO', 'sede@der.sp.gov.br')

# ============================================
# CONFIGURAÇÃO DO WHOOSH
# ============================================
CAMINHO_INDICE = "indice_funcionarios"
if not os.path.exists(CAMINHO_INDICE):
    os.mkdir(CAMINHO_INDICE)
    ix = create_in(CAMINHO_INDICE, schema)
else:
    ix = open_dir(CAMINHO_INDICE)

app.config['WHOOSH_IX'] = ix

# ============================================
# FUNÇÕES AUXILIARES
# ============================================
PERFIS_TODOS = {'CA.9', 'SA.9'}
PERFIS_TERCEIRO_AREA = {'CGR.9', 'CO.9', 'CT.9'}
AUDITORIA_MAX_CHAVES = 30
AUDITORIA_MAX_ITENS_LISTA = 20
AUDITORIA_MAX_TEXTO = 160
AUDITORIA_EXTENSOES_IGNORADAS = (
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico',
    '.css', '.js', '.map', '.woff', '.woff2', '.ttf', '.eot',
)
AUDITORIA_ROTAS_IGNORADAS = {'/healthz', '/readyz', '/metrics'}

def _env_int(nome: str, padrao: int) -> int:
    bruto =(os.getenv(nome, '') or '').strip()
    if not bruto:
        return padrao
    try:
        return int(bruto)
    except ValueError:
        return padrao

app.config['AUDIT_RETENCAO_DIAS_GERAL']= _env_int('AUDIT_RETENCAO_DIAS_GERAL', 365)
app.config['AUDIT_RETENCAO_DIAS_SEGURANCA'] = _env_int('AUDIT_RETENCAO_DIAS_SEGURANCA', 1825)
app.config['AUDIT_RETENCAO_DIAS_ALERTA'] = _env_int('AUDIT_RETENCAO_DIAS_ALERTA', 3650)

_METRICAS_LOCK = Lock()
_METRICAS = Counter()
_LATENCIA_BUCKETS_MS = (50, 100, 250, 500, 1000, 2000, 5000)
_LATENCIA_HIST = Counter()


def _rotulo_rota_metricas() -> str:
    if request.endpoint:
        return request.endpoint
    return request.path or 'desconhecida'


def _registrar_metricas_requisicao(response, duracao_ms: float | None = None):
    rota = _rotulo_rota_metricas()
    status = str(response.status_code)
    metodo = request.method.upper()

    with _METRICAS_LOCK:
        _METRICAS['http_requests_total'] += 1
        _METRICAS[f'http_requests_by_method_total|{metodo}'] += 1
        _METRICAS[f'http_requests_by_status_total|{status}'] += 1
        _METRICAS[f'http_requests_by_route_total|{rota}'] += 1

        if response.status_code >= 500:
            _METRICAS['http_server_errors_total'] += 1
        elif response.status_code >= 400:
            _METRICAS['http_client_errors_total'] += 1

        if duracao_ms is not None:
            _METRICAS['http_request_duration_ms_sum'] += duracao_ms
            _METRICAS['http_request_duration_ms_count'] += 1
            limite_b = next((b for b in _LATENCIA_BUCKETS_MS if duracao_ms <= b), 'inf')
            _LATENCIA_HIST[f'http_request_duration_ms_bucket|{limite_b}'] += 1
            _LATENCIA_HIST['http_request_duration_ms_bucket|+Inf'] += 1

        if request.endpoint == "static":
            return response

    return response


def _formatar_metricas_prometheus() -> str:
    with _METRICAS_LOCK:
        linhas = [
            '# HELP http_requests_total Total de requisicoes HTTP.',
            '# TYPE http_requests_total counter',
            f'http_requests_total {_METRICAS.get("http_requests_total", 0)}',
            '# HELP http_requests_by_method_total Total de requisicoes por metodo HTTP.',
            '# TYPE http_requests_by_method_total counter',
            '# HELP http_requests_by_status_total Total de requisicoes por status HTTP.',
            '# TYPE http_requests_by_status_total counter',
            '# HELP http_requests_by_route_total Total de requisicoes por rota.',
            '# TYPE http_requests_by_route_total counter',
            '# HELP http_server_errors_total Total de respostas 5xx.',
            '# TYPE http_server_errors_total counter',
            f'http_server_errors_total {_METRICAS.get("http_server_errors_total", 0)}',
            '# HELP http_client_errors_total Total de respostas 4xx.',
            '# TYPE http_client_errors_total counter',
            f'http_client_errors_total {_METRICAS.get("http_client_errors_total", 0)}',
            '# HELP http_request_duration_ms Latencia das requisicoes em milissegundos.',
            '# TYPE http_request_duration_ms histogram',
        ]

        for key, valor in sorted(_METRICAS.items()):
            if '|' in key:
                base, sufixo = key.split('|', 1)
                if base == 'http_requests_by_method_total':
                    linhas.append(f'{base}{{method="{sufixo}"}} {valor}')
                elif base == 'http_requests_by_status_total':
                    linhas.append(f'{base}{{status="{sufixo}"}} {valor}')
                elif base == 'http_requests_by_route_total':
                    linhas.append(f'{base}{{route="{sufixo}"}} {valor}')

        if _METRICAS.get('http_request_duration_ms_count', 0):
            linhas.append(f'http_request_duration_ms_sum {_METRICAS.get("http_request_duration_ms_sum", 0):.2f}')
            linhas.append(f'http_request_duration_ms_count {_METRICAS.get("http_request_duration_ms_count", 0)}')
            acumulado = 0
            for bucket in (*_LATENCIA_BUCKETS_MS, 'inf'):
                acumulado += _LATENCIA_HIST.get(f'http_request_duration_ms_bucket|{bucket}', 0)
                le = '+Inf' if bucket == 'inf' else bucket
                linhas.append(f'http_request_duration_ms_bucket{{le="{le}"}} {acumulado}')
        else:
            linhas.append('http_request_duration_ms_sum 0')
            linhas.append('http_request_duration_ms_count 0')
            for bucket in (*_LATENCIA_BUCKETS_MS, 'inf'):
                le = '+Inf' if bucket == 'inf' else bucket
                linhas.append(f'http_request_duration_ms_bucket{{le="{le}"}} 0')

    return '\n'.join(linhas) + '\n'

def _limitar_texto_auditoria(valor: Any, limite: int = AUDITORIA_MAX_TEXTO) -> str:
    texto = str(valor)
    return texto[:limite]


def _normalizar_json_auditoria(valor: Any, profundidade: int = 0) -> Any:
    if profundidade >= 3:
        return '[profundidade_maxima]'

    if isinstance(valor, dict):
        itens = list(valor.items())
        saida: dict[str, Any] = {}
        for idx, (chave, conteudo) in enumerate(itens):
            if idx >= AUDITORIA_MAX_CHAVES:
                saida['__campos_excedentes__'] = len(itens) - AUDITORIA_MAX_CHAVES
                break
            saida[str(chave)] = _normalizar_json_auditoria(conteudo, profundidade + 1)
        return saida

    if isinstance(valor, list):
        itens = valor[:AUDITORIA_MAX_ITENS_LISTA]
        saida = [_normalizar_json_auditoria(item, profundidade + 1) for item in itens]
        if len(valor) > AUDITORIA_MAX_ITENS_LISTA:
            saida.append(f'... +{len(valor) - AUDITORIA_MAX_ITENS_LISTA} itens')
        return saida

    if isinstance(valor, tuple):
        itens = list(valor[:AUDITORIA_MAX_ITENS_LISTA])
        saida = [_normalizar_json_auditoria(item, profundidade + 1) for item in itens]
        if len(valor) > AUDITORIA_MAX_ITENS_LISTA:
            saida.append(f'... +{len(valor) - AUDITORIA_MAX_ITENS_LISTA} itens')
        return saida

    if isinstance(valor, (str, int, float, bool)) or valor is None:
        if isinstance(valor, str):
            return _limitar_texto_auditoria(valor)
        return valor

    if hasattr(valor, 'isoformat'):
        return valor.isoformat()

    return _limitar_texto_auditoria(valor)


def _capturar_multidict_auditoria(multidict) -> dict[str, Any]:
    if not multidict:
        return {}

    chaves = sorted(multidict.keys())
    dados: dict[str, Any] = {}

    for idx, chave in enumerate(chaves):
        if idx >= AUDITORIA_MAX_CHAVES:
            dados['__campos_excedentes__'] = len(chaves) - AUDITORIA_MAX_CHAVES
            break

        valores = multidict.getlist(chave)
        if len(valores) <= 1:
            dados[chave] = _limitar_texto_auditoria(valores[0] if valores else '')
            continue

        itens = [_limitar_texto_auditoria(v) for v in valores[:AUDITORIA_MAX_ITENS_LISTA]]
        if len(valores) > AUDITORIA_MAX_ITENS_LISTA:
            itens.append(f'... +{len(valores) - AUDITORIA_MAX_ITENS_LISTA} itens')
        dados[chave] = itens

    return dados


def _acao_auditoria_requisicao() -> str:
    endpoint = (request.endpoint or 'endpoint_desconhecido').replace('.', '_')
    endpoint = re.sub(r'[^A-Za-z0-9_]+', '_', endpoint).upper()
    return f'HTTP_{request.method.upper()}_{endpoint}'


def _detalhes_requisicao_auditoria(status_code: int, duracao_ms: int | None) -> dict[str, Any]:
    detalhes: dict[str, Any] = {
        'endpoint': request.endpoint or '',
        'status_code': status_code,
        'duracao_ms': duracao_ms,
        'query_params': _capturar_multidict_auditoria(request.args),
    }

    if request.method.upper() in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        if request.is_json:
            detalhes['payload_json'] = _normalizar_json_auditoria(request.get_json(silent=True))
        else:
            detalhes['form_data'] = _capturar_multidict_auditoria(request.form)

        arquivos = sorted(request.files.keys())
        if arquivos:
            detalhes['arquivos'] = arquivos[:AUDITORIA_MAX_ITENS_LISTA]

    return detalhes


def _deve_ignorar_auditoria_requisicao() -> bool:
    caminho = (request.path or '').lower()
    if request.endpoint == 'static' or caminho.startswith('/static/'):
        return True
    if caminho.endswith(AUDITORIA_EXTENSOES_IGNORADAS):
        return True
    if caminho in AUDITORIA_ROTAS_IGNORADAS:
        return True
    return False

def tratar_nao_se_aplica(valor: Any) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    if s.lower() in {'não se aplica', 'nao se aplica', 'n/a', 'na'}:
        return None
    return s


def normalizar_ramal(valor: Any) -> str:
    if valor is None:
        return ''
    s = re.sub(r'\D', '', str(valor))
    if not s:
        return ''
    if s.startswith('173218'):
        return s
    return '173218' + s

def normalizar_titulo_simples(valor: Any) -> str:
    """Texto: primeira letra de cada palavra em maiúsculo (sem preservar siglas)."""
    if valor is None:
        return ''

    s = str(valor).strip()

    if not s or s.lower() in ('none', 'nan', 'nat'):
        return ''

    palavras = re.split(r'\s+', s)
    saida = []

    for palavra in palavras:
        partes = re.split(r"([-/'])", palavra)
        nova = []

        for parte in partes:
            if parte in "-/'":
                nova.append(parte)
                continue

            if not parte:
                continue

            nova.append(parte.capitalize())

        saida.append(''.join(nova))

    return ' '.join(saida)


def valor_exportacao(func, campo):
    valor = getattr(func, campo, None)

    campos_so_servidor = {
        'matricula',
    }

    campos_so_terceirizado = {
        'empresa_contratada',
        'numero_contrato',
        'gestor_contrato',
        'fiscal_tecnico',
        'fiscal_administrativo',
        'preposto',
    }

    if func.vinculo == 'SERVIDOR' and campo in campos_so_terceirizado:
        return 'Não se aplica'

    if func.vinculo == 'TERCEIRIZADO' and campo in campos_so_servidor:
        return 'Não se aplica'

    if valor is None or valor == '':
        return ''

    return valor

def valor_exportacao_resultado(resultado, campo):
    valor = resultado.get(campo, None)
    vinculo = str(resultado.get('vinculo', '')).upper()

    campos_so_servidor = {
        'matricula',
    }

    campos_so_terceirizado = {
        'empresa_contratada',
        'numero_contrato',
        'gestor_contrato',
        'fiscal_tecnico',
        'fiscal_administrativo',
        'preposto',
    }

    if vinculo == 'SERVIDOR' and campo in campos_so_terceirizado:
        return 'Não se aplica'

    if vinculo == 'TERCEIRIZADO' and campo in campos_so_servidor:
        return 'Não se aplica'

    if valor is None:
        return ''

    return valor

def limpar_valor_excel(val: Any) -> Any:
    if val is None:
        return ''

    if isinstance(val, str):
        val = val.strip()

        if val.lower() == 'none':
            return ''

        if val.lower() == 'nat':
            return ''

        if val == '':
            return ''

    return val


def parse_date(date_str: Any) -> date | None:
    if date_str:
        try:
            return datetime.strptime(str(date_str), '%Y-%m-%d').date()
        except ValueError:
            return None
    return None


def parse_excel_date(valor: Any) -> date | None:
    if valor is None or pd.isna(valor):
        return None
    try:
        return pd.to_datetime(valor).date()
    except Exception:
        return None


def date_to_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    return val


def montar_lotacao(form, prefixo=''):
    lotacao_direta = tratar_nao_se_aplica(form.get(f'{prefixo}lotacao'))
    if lotacao_direta:
        return normalizar_titulo(lotacao_direta)

    ua = tratar_nao_se_aplica(form.get(f'{prefixo}ua'))
    ua_cargo_origem = tratar_nao_se_aplica(form.get(f'{prefixo}ua_cargo_origem'))

    partes = []
    if ua_cargo_origem:
        partes.append(str(ua_cargo_origem).strip())
    if ua:
        partes.append(f"UA {str(ua).strip()}")

    if not partes:
        return ''
    return normalizar_titulo(' - '.join(partes))


def obter_email_institucional(form, prefixo=''):
    email = (form.get(f'{prefixo}email_institucional') or '').strip()
    return email or EMAIL_SEDE_PADRAO


def obter_perfil_usuario(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    perfil_raw = (user.perfil or user.login or '').strip()
    return perfil_raw.upper()


def obter_area_permissao(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    # Mantido por compatibilidade. Se não houver modelo de permissão por área, retorna vazio.
    return ''

def is_safe_url(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@app.after_request
def adicionar_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline'; img-src 'self' data:;"
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.before_request
def iniciar_auditoria_requisicao():
    g.audit_inicio = datetime.now(UTC)
    # request_id compartilhado para logs e auditoria
    if not hasattr(g, "audit_request_id"):
        # reusa o id se já existir em algum fluxo; caso contrário gera
        g.audit_request_id = getattr(g, "audit_request_id", None) or os.urandom(16).hex()


@app.after_request
def auditar_requisicao(response):
    try:
        if _deve_ignorar_auditoria_requisicao():
            return response

        inicio = getattr(g, 'audit_inicio', None)
        duracao_ms = None
        if inicio:
            duracao_ms = int((datetime.now(UTC) - inicio).total_seconds() * 1000)

        status_http = int(response.status_code)
        status_evento = 'sucesso' if status_http < 400 else 'falha'
        categoria = 'acesso' if request.method.upper() in {'GET', 'HEAD', 'OPTIONS'} else 'operacao'

        registrar_evento_seguro(
            _acao_auditoria_requisicao(),
            categoria=categoria,
            status=status_evento,
            recurso=request.blueprint or 'app',
            recurso_id=request.endpoint or request.path,
            detalhes=_detalhes_requisicao_auditoria(status_http, duracao_ms),
        )
    except Exception:
        pass

    return response

@app.before_request
def iniciar_timer():
    g.request_inicio = perf_counter()

@app.after_request
def registrar_metricas(response):
    inicio = getattr(
        g,
        "request_inicio",
        None
    )

    # Métricas Prometheus (counter/histograma) já preparadas no arquivo
    # Observação: duracao_ms calculada logo abaixo.

    if inicio is None:
        return response

    duracao_ms = round(
        (perf_counter() - inicio) * 1000,
        2
    )

    _registrar_metricas_requisicao(response, duracao_ms=duracao_ms)

    current_app.logger.info(
        f"{request.method} {request.path} {response.status_code} {duracao_ms}ms"
    )

    if duracao_ms > 2000:
        registrar_evento_seguro(
            "APP_ENDPOINT_LENTO",
            categoria="observabilidade",
            status="sucesso",
            recurso=request.path,
            detalhes={
                "duracao_ms": duracao_ms,
                "status_code": response.status_code,
                "metodo": request.method,
                "endpoint": request.path,

            }
        )

    if response.status_code >= 500 and not getattr(g, "erro_ja_registrado", False):
        registrar_evento_seguro(
            "APP_ENDPOINT_ERRO",
            categoria="observabilidade",
            status="falha",
            recurso=request.path,
            detalhes={
                "status_code": response.status_code,
                "duracao_ms": duracao_ms,
                "metodo": request.method,
                "endpoint": request.path,
                "query_params": dict(request.args)
            }
        )

    return response

@app.errorhandler(429)
def limite_excedido(e):
    return render_template("429.html"), 429

@app.errorhandler(RequestEntityTooLarge)
def upload_excedido(e):
    registrar_evento_seguro(
        "APP_UPLOAD_EXCEDIDO",
        categoria="seguranca",
        status="falha",
        recurso=request.path,
        detalhes={
            "limite_mb": round(
                app.config["MAX_CONTENT_LENGTH"] / 1024 / 1024,
                2
            ),
            "content_length": request.content_length,
        }
    )
    flash(
        "Arquivo excede o tamanho máximo permitido",
        "error"
    )

    return redirect(
        request.referrer or url_for("painel")
    )

@app.errorhandler(Exception)
def erro_global(e):

    if isinstance(e, HTTPException):
        return e

    g.erro_ja_registrado = True

    registrar_evento_seguro(
        "APP_ERRO_INTERNO",
        categoria="observabilidade",
        status="falha",
        recurso=request.path,
        detalhes={
            "erro": str(e),
            "tipo_erro": type(e).__name__
        }
    )

    current_app.logger.exception(
        "Erro interno não tratado"
    )

    raise e
# ============================================
# FILTROS JINJA2
# ============================================
@app.template_filter('formato_cpf')
def formato_cpf_filter(s):
    return formatar_cpf(s)


@app.template_filter('formato_rg')
def formato_rg_filter(s):
    return formatar_rg(s)

# ============================================
# WHOOSH
# ============================================
def reindexar_funcionario(funcionario):
    print(f"🔄 Reindexando funcionário: {funcionario.nome_completo} - CPF: {funcionario.cpf}")
    writer = ix.writer()
    writer.delete_by_term('id', str(funcionario.id))

    if funcionario.ativo:
        writer.add_document(
            id=str(funcionario.id),
            matricula=funcionario.matricula or '',
            cpf=normalizar_cpf(funcionario.cpf),
            rg=normalizar_rg(funcionario.rg or ''),
            nome_completo=normalizar_titulo(funcionario.nome_completo),
            data_nasc=date_to_datetime(funcionario.data_nasc),

            vinculo=normalizar_maiusculo(funcionario.vinculo),
            tipo=normalizar_maiusculo(funcionario.tipo or ''),
            subtipo_vinculo=normalizar_maiusculo(funcionario.subtipo_vinculo or ''),
            forma_ingresso=normalizar_titulo(funcionario.forma_ingresso or ''),

            cargo_exercicio=normalizar_titulo(funcionario.cargo_exercicio or ''),
            cargo_origem=normalizar_titulo(funcionario.cargo_origem or ''),

            lotacao=normalizar_titulo(funcionario.lotacao or ''),
            area=normalizar_titulo(funcionario.area or ''),
            coordenadoria=normalizar_maiusculo(funcionario.coordenadoria or ''),

            data_ingresso_der=date_to_datetime(funcionario.data_ingresso_der),
            data_inicio=date_to_datetime(funcionario.data_inicio),
            data_admissao=date_to_datetime(funcionario.data_admissao),
            data_desligamento=date_to_datetime(funcionario.data_desligamento),

            email_institucional=(funcionario.email_institucional or '').strip(),
            email_pessoal=(funcionario.email_pessoal or '').strip(),
            telefone_pessoal=(funcionario.telefone_pessoal or '').strip(),
            ramal=(funcionario.ramal or '').strip(),

            cin=(funcionario.cin or '').strip(),
            titulo_eleitor=(funcionario.titulo_eleitor or '').strip(),
            pis_pasep=(funcionario.pis_pasep or '').strip(),
            prontuario_funcional=(funcionario.prontuario_funcional or '').strip(),
            situacao=normalizar_titulo(funcionario.situacao or ''),
            doe_portaria=(funcionario.doe_portaria or '').strip(),

            empresa_contratada=normalizar_titulo_simples(funcionario.empresa_contratada or ''),
            numero_contrato=(funcionario.numero_contrato or '').strip(),
            gestor_contrato=normalizar_titulo(funcionario.gestor_contrato or ''),
            fiscal_tecnico=normalizar_titulo(funcionario.fiscal_tecnico or ''),
            fiscal_administrativo=normalizar_titulo(funcionario.fiscal_administrativo or ''),
            preposto=normalizar_titulo(funcionario.preposto or '')
        )

    writer.commit()
    print("   ✅ Índice atualizado")


def reindexar_todos():
    global ix

    if ix:
        ix.close()

    try:
        if os.path.exists(CAMINHO_INDICE):
            shutil.rmtree(CAMINHO_INDICE)
        os.mkdir(CAMINHO_INDICE)
        ix = create_in(CAMINHO_INDICE, schema)
    except Exception as e:
        print(f"⚠️ Erro ao remover pasta do índice: {e}")
        ix = open_dir(CAMINHO_INDICE)
        writer = ix.writer()
        writer.delete_by_query(Every())
        writer.commit()

    app.config['WHOOSH_IX'] = ix
    writer = ix.writer()

    for func in Funcionario.query.filter_by(ativo=True).all():
        writer.add_document(
            id=str(func.id),
            matricula=func.matricula or '',
            cpf=normalizar_cpf(func.cpf),
            rg=normalizar_rg(func.rg or ''),
            nome_completo=normalizar_titulo(func.nome_completo),
            data_nasc=date_to_datetime(func.data_nasc),

            vinculo=normalizar_maiusculo(func.vinculo),
            tipo=normalizar_maiusculo(func.tipo or ''),
            subtipo_vinculo=normalizar_maiusculo(func.subtipo_vinculo or ''),
            forma_ingresso=normalizar_titulo(func.forma_ingresso or ''),

            cargo_exercicio=normalizar_titulo(func.cargo_exercicio or ''),
            cargo_origem=normalizar_titulo(func.cargo_origem or ''),

            lotacao=normalizar_titulo(func.lotacao or ''),
            area=normalizar_titulo(func.area or ''),
            coordenadoria=normalizar_maiusculo(func.coordenadoria or ''),

            data_ingresso_der=date_to_datetime(func.data_ingresso_der),
            data_inicio=date_to_datetime(func.data_inicio),
            data_admissao=date_to_datetime(func.data_admissao),
            data_desligamento=date_to_datetime(func.data_desligamento),

            email_institucional=(func.email_institucional or '').strip(),
            email_pessoal=(func.email_pessoal or '').strip(),
            telefone_pessoal=(func.telefone_pessoal or '').strip(),
            ramal=(func.ramal or '').strip(),

            cin=(func.cin or '').strip(),
            titulo_eleitor=(func.titulo_eleitor or '').strip(),
            pis_pasep=(func.pis_pasep or '').strip(),
            prontuario_funcional=(func.prontuario_funcional or '').strip(),
            situacao=normalizar_titulo(func.situacao or ''),
            doe_portaria=(func.doe_portaria or '').strip(),

            empresa_contratada=normalizar_titulo_simples(func.empresa_contratada or ''),
            numero_contrato=(func.numero_contrato or '').strip(),
            gestor_contrato=normalizar_titulo(func.gestor_contrato or ''),
            fiscal_tecnico=normalizar_titulo(func.fiscal_tecnico or ''),
            fiscal_administrativo=normalizar_titulo(func.fiscal_administrativo or ''),
            preposto=normalizar_titulo(func.preposto or '')
        )

    writer.commit()
    app.config['WHOOSH_IX'] = ix

# ============================================
# CRIAÇÃO DAS TABELAS E ADMIN
# ============================================
with app.app_context():
    try:
        db.create_all()

        admin = Usuario.query.filter_by(login='admin').first()
        if not admin:
            admin = Usuario(login='admin', is_admin=True, is_superadmin=True, perfil='CA.9')
            admin.set_password(os.getenv('ADMIN_PASSWORD', 'troque-essa-senha'))
            db.session.add(admin)
            db.session.commit()
        else:
            alterado = False

            if not admin.is_admin:
                admin.is_admin = True
                alterado = True

            if not admin.is_superadmin:
                admin.is_superadmin = True
                alterado = True

            if not admin.perfil:
                admin.perfil = 'CA.9'
                alterado = True

            if alterado:
                db.session.commit()
    except Exception as e:
        app.logger.error(
            f"Falha no bootstrap do banco: {e}"
        )


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


def _readiness_status() -> tuple[bool, dict[str, str]]:
    pronto = True
    detalhes: dict[str, str] = {}

    try:
        db.session.execute(text("SELECT 1"))
        detalhes["database"] = "ok"
    except Exception:
        db.session.rollback()
        detalhes["database"] = "erro"
        pronto = False

    indice_ok = os.path.isdir(CAMINHO_INDICE) and app.config.get('WHOOSH_IX') is not None
    detalhes["indice"] = "ok" if indice_ok else "erro"
    if not indice_ok:
        pronto = False

    return pronto, detalhes

@app.get('/healthz')
def healthz():
    current_app.logger.info(
        "healthz ok",
        extra={
            "category": "observabilidade",
            "request_id": getattr(g, "audit_request_id", None),
            "method": request.method,
            "path": request.path,
            "status_code": 200,
            "duration_ms": None,
            "ip": request.headers.get("X-Forwarded-For", request.remote_addr) or "",
        }
    )
    return jsonify({"status": "ok"}), 200


@app.get('/readyz')
def readyz():
    pronto, detalhes = _readiness_status()
    current_app.logger.info(
        f"readyz {'ready' if pronto else 'not_ready'}",
        extra={
            "category": "observabilidade",
            "database": detalhes.get("database"),
            "indice": detalhes.get("indice")
        }
    )
    payload ={"status": "ready" if pronto else "not_ready", **detalhes}
    return jsonify(payload), (200 if pronto else 503)

@app.get('/metrics')
def metrics():
    # Resposta Prometheus dos contadores/histogramas em memória
    return _formatar_metricas_prometheus(), 200, {
        "Content-Type": "text/plain; version=0.0.4; charset=utf-8"
    }

# ============================================
# ROTAS ADMINISTRATIVAS
# ============================================

@app.route('/painel')
@login_required
@audit_event()
def painel():
    print(app.logger.handlers)
    perfil = obter_perfil_usuario(current_user)
    ordem_nome = (
        func.lower(func.trim(func.coalesce(Funcionario.nome_completo, ''))),
        Funcionario.id.asc(),
    )

    if current_user.is_superadmin or perfil in PERFIS_TODOS:
        funcionarios = Funcionario.query.order_by(*ordem_nome).all()
    elif perfil in {'CGR.9', 'CO.9', 'CT.9'}:
        coord = perfil.upper()
        funcionarios = Funcionario.query.filter(
            func.upper(Funcionario.vinculo) == 'TERCEIRIZADO',
            or_(
                func.upper(func.coalesce(Funcionario.coordenadoria, '')).like(f'%{coord}%'),
                func.upper(func.coalesce(Funcionario.area, '')).like(f'%{coord}%'),
                func.upper(func.coalesce(Funcionario.lotacao, '')).like(f'%{coord}%'),
            )
        ).order_by(*ordem_nome).all()
    else:
        funcionarios = []

    return render_template('painel.html', funcionarios=funcionarios)

@app.route('/observabilidade')
@login_required
@superadmin_required
@audit_event()
def observabilidade():

    with _METRICAS_LOCK:
        request_total = _METRICAS.get(
            'http_requests_total',
            0
        )

        errors_4xx = _METRICAS.get(
            'http_client_errors_total',
            0
        )

        errors_5xx = _METRICAS.get(
            'http_server_errors_total',
            0
        )

        soma = _METRICAS.get(
            'http_request_duration_ms_sum',
            0
        )

        count = _METRICAS.get(
            'http_request_duration_ms_count',
            0
        )

    latencia_media = round(
        soma/count,
        2
    )if count else 0

    top_rotas = []

    with _METRICAS_LOCK:
        for chave, valor in _METRICAS.items():

            if chave.startswith(
                "http_requests_by_route_total|"
            ):

                rota = chave.split("|", 1)[1]

                if rota not in [
                    "static",
                    "observabilidade",
                    "metrics",
                    "healthz",
                    "readyz"
                ]:
                    top_rotas.append(
                        (rota, valor)
                    )

    top_rotas.sort(
        key=lambda x: x[1],
        reverse=True
    )

    uptime_segundos = int(
        (datetime.now(UTC) - APP_START_TIME).total_seconds()
    )

    horas = uptime_segundos // 3600
    minutos = (uptime_segundos % 3600) // 60
    segundos = uptime_segundos % 60

    uptime_formatado = f"{horas}h {minutos}m {segundos}s"

    pronto, detalhes = _readiness_status()

    return render_template(
        'observabilidade.html',
        request_total=request_total,
        errors_4xx=errors_4xx,
        errors_5xx=errors_5xx,
        latencia_media=latencia_media,
        top_rotas=top_rotas[:10],
        pronto=pronto,
        detalhes=detalhes,
        uptime=uptime_formatado
    )
# ============================================
# MIGRAÇÃO / IMPORTAÇÃO
# ============================================
@app.route('/migrar')
@login_required
@audit_event()
def migrar_dados():
    flash('A rota /migrar precisa ser adaptada para a planilha única nova antes do uso.', 'warning')
    return redirect(url_for('painel'))

# INICIALIZAÇÃO
# ============================================
if __name__ == '__main__':
    from waitress import serve
    porta = int(os.getenv('PORT', '8080'))
    serve(app, host='0.0.0.0', port=porta)
