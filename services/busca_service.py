from whoosh.qparser import MultifieldParser
from whoosh.query import Term, Or, Every, And
from whoosh.query.qcore import QueryError

from services.normalizacao_service import normalizar_cpf, normalizar_rg, normalizar_maiusculo, escape_whoosh_query
from flask_login import current_user

PERFIS_TODOS = {'CA.9', 'SA.9'}
PERFIS_TERCEIRO_COORD = {'CGR.9', 'CO.9', 'CT.9'}


def _prioridade_vinculo(resultado):
    vinculo = str(resultado.get("vinculo", "") or "").upper()
    if vinculo == "SERVIDOR":
        return 0
    if vinculo == "TERCEIRIZADO":
        return 1
    return 2


def _chave_ordenacao(resultado, separar_por_vinculo=False):
    chave_base = (
        str(resultado.get("nome_completo", "") or "").strip().casefold(),
        str(resultado.get("cpf", "") or "").strip(),
    )
    if separar_por_vinculo:
        return (_prioridade_vinculo(resultado),) + chave_base
    return chave_base


def obter_perfil_usuario(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    perfil_raw = (user.perfil or user.login or '').strip()
    return perfil_raw.upper()


def obter_coordenadoria_permissao(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return ''

    perfil = obter_perfil_usuario(user)

    if perfil in PERFIS_TERCEIRO_COORD:
        return perfil

    return ''


def _resultado_permitido_por_coordenadoria(resultado, coord_req):
    if not coord_req:
        return False

    coord_upper = coord_req.upper()
    coord_val = str(resultado.get("coordenadoria", "") or "").upper()
    area_val = str(resultado.get("area", "") or "").upper()
    lotacao_val = str(resultado.get("lotacao", "") or "").upper()

    return (
        coord_upper in coord_val
        or coord_upper in area_val
        or coord_upper in lotacao_val
    )


def executar_busca(ix, query, vinculo_selecionado):
    with ix.searcher() as searcher:
        coord_req_usuario = ''
        separar_por_vinculo = not vinculo_selecionado or vinculo_selecionado.lower() == 'todos'

        if query:
            query_cpf = normalizar_cpf(query)
            query_rg = normalizar_rg(query)

            campos_pesquisa = [
                "nome_completo", "cpf", "rg", "matricula", "cargo_exercicio",
                "cargo_origem", "lotacao", "area", "coordenadoria",
                "empresa_contratada", "numero_contrato", "subtipo_vinculo",
                "email_institucional", "ramal", "situacao",
                "prontuario_funcional", "doe_portaria"
            ]

            parser = MultifieldParser(campos_pesquisa, schema=ix.schema)
            try:
                q_obj = parser.parse(escape_whoosh_query(query))
            except QueryError:
                q_obj = parser.parse(escape_whoosh_query(query.replace('"', '')))

            extras = []
            if query_cpf:
                extras.append(Term("cpf", query_cpf))
            if query_rg:
                extras.append(Term("rg", query_rg))
            if extras:
                q_obj = Or([q_obj] + extras)
        else:
            q_obj = Every()

        if vinculo_selecionado and vinculo_selecionado.lower() != 'todos':
            q_vinculo = Term("vinculo", normalizar_maiusculo(vinculo_selecionado))
            q_obj = And([q_obj, q_vinculo])

        if current_user.is_authenticated:
            perfil = obter_perfil_usuario(current_user)

            if perfil in PERFIS_TODOS or (current_user.is_admin and not (current_user.perfil or '').strip()):
                q_final = q_obj
            elif perfil in PERFIS_TERCEIRO_COORD:
                coord_req = obter_coordenadoria_permissao(current_user)
                if not coord_req:
                    q_final = Term("id", "__no_access__")
                else:
                    coord_req_usuario = coord_req
                    q_final = And([
                        q_obj,
                        Term("vinculo", "TERCEIRIZADO"),
                    ])
            else:
                q_final = Term("id", "__no_access__")
        else:
            q_final = Term("id", "__no_access__")

        results = searcher.search(q_final, limit=None)
        resultados = [dict(r) for r in results]

        if coord_req_usuario:
            resultados = [
                r for r in resultados
                if _resultado_permitido_por_coordenadoria(r, coord_req_usuario)
            ]

        if not query:
            resultados.sort(key=lambda r: _chave_ordenacao(r, separar_por_vinculo))
            return resultados

        q_lower = query.lower()
        query_cpf = normalizar_cpf(query)
        query_rg = normalizar_rg(query)

        campos_verificar = [
            "nome_completo", "cpf", "rg", "matricula", "cargo_exercicio",
            "cargo_origem", "lotacao", "area", "coordenadoria",
            "empresa_contratada", "numero_contrato", "subtipo_vinculo",
            "email_institucional", "ramal", "situacao",
            "prontuario_funcional", "doe_portaria"
        ]

        resultados_finais = []
        for r in resultados:
            for c in campos_verificar:
                val = str(r.get(c, '')).lower()
                if q_lower in val or (query_cpf and query_cpf in val) or (query_rg and query_rg in val):
                    resultados_finais.append(r)
                    break

        resultados_finais.sort(key=lambda r: _chave_ordenacao(r, separar_por_vinculo))
        return resultados_finais
