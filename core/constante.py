"""
Constantes utilizadas em todo o SIST.

Este módulo centraliza todas as listas de opções utilizadas nos
formulários, importações, validações e normalização de dados.
"""

# ==========================================================
# VÍNCULO
# ==========================================================

OPCOES_VINCULO = [
    "SERVIDOR",
    "TERCEIRIZADO",
]

# ==========================================================
# TIPO
# ==========================================================

OPCOES_TIPO = [
    "EFETIVO",
    "CELETISTA",
    "COMISSIONADO",
    "CELETISTA ESTÁVEL",
    "TERCEIRIZADO",
]

# ==========================================================
# SUBTIPO DE VÍNCULO
# ==========================================================

OPCOES_SUBTIPO_VINCULO = [
    "ADMINISTRATIVO",
    "OPERACIONAL",
]

# ==========================================================
# FORMA DE INGRESSO
# ==========================================================

OPCOES_FORMA_INGRESSO = [
    "Concurso Público",
    "Lei 500/74",
    "Livre Provimento",
    "Optou 100% Subsídio",
    "Prestador de Serviço",
    "Processo Seletivo",
]

# ==========================================================
# SITUAÇÃO
# ==========================================================

OPCOES_SITUACAO = [
    "Ativo",
    "Inativo - Exoneração",
    "Inativo - Demissão",
    "Inativo - Aposentadoria",
    "Inativo - Término de contrato",
    "Inativo - Outros",
]

# ==========================================================
# COORDENADORIAS
# ==========================================================

OPCOES_COORDENADORIA = [

    "38.842 - COORDENADORIA GERAL REGIONAL - CGR.9",

    "38.844 - COORDENADORIA ADMINISTRATIVA - CA.9",

    "38.886 - COORDENADORIA DE CONSERVAÇÃO E OPERAÇÕES VIÁRIAS - CO.9",

    "38.922 - COORDENADORIA TÉCNICA - CT.9",
]

# ==========================================================
# ÁREAS
# ==========================================================

OPCOES_AREA = [

    "38.842 - COORDENADORIA GERAL REGIONAL - CGR.9",

    "38.844 - COORDENADORIA ADMINISTRATIVA - CA.9",

    "38.886 - COORDENADORIA DE CONSERVAÇÃO E OPERAÇÕES VIÁRIAS - CO.9",

    "38.922 - COORDENADORIA TÉCNICA - CT.9",

    "38.846 - SERVIÇO DE ADMINISTRAÇÃO DE PESSOAL - SA.9",

    "38.867 - SERVIÇO DE AQUISIÇÕES E CONTRATAÇÕES - SQ.9",

    "38.851 - SERVIÇO DE FINANÇAS - SF.9",

    "38.869 - SERVIÇO DE PATRIMÔNIO, TECNOLOGIA E ATIVIDADES GERAIS - SG.9",

    "36.759 - SERVIÇO DE FAIXA DE DOMÍNIO, PEDÁGIOS, RADAR E BALANÇA - SR.9",

    "36.765 - SERVIÇO DE UNIDADE BÁSICA DE ATENDIMENTO - UBA - SB.9",

    "36.766 - SERVIÇO DE CONSERVAÇÃO DE ROTINA - SC.9",

    "36.767 - SERVIÇO DE CONSTRUÇÃO - ST.9",

    "36.768 - SERVIÇO DE PLANEJAMENTO E PROJETOS - SP.9",

    "SERVIÇO EXTERNO",
]

# ==========================================================
# LOTAÇÕES
# ==========================================================

OPCOES_LOTACAO = [

    "38.842 - COORDENADORIA GERAL REGIONAL - CGR.9",

    "38.844 - COORDENADORIA ADMINISTRATIVA - CA.9",

    "38.886 - COORDENADORIA DE CONSERVAÇÃO E OPERAÇÕES VIÁRIAS - CO.9",

    "38.922 - COORDENADORIA TÉCNICA - CT.9",

    "38.846 - SERVIÇO DE ADMINISTRAÇÃO DE PESSOAL - SA.9",

    "38.867 - SERVIÇO DE AQUISIÇÕES E CONTRATAÇÕES - SQ.9",

    "38.851 - SERVIÇO DE FINANÇAS - SF.9",

    "38.869 - SERVIÇO DE PATRIMÔNIO, TECNOLOGIA E ATIVIDADES GERAIS - SG.9",

    "36.759 - SERVIÇO DE FAIXA DE DOMÍNIO, PEDÁGIOS, RADAR E BALANÇA - SR.9",

    "36.765 - SERVIÇO DE UNIDADE BÁSICA DE ATENDIMENTO - UBA - SB.9",

    "36.766 - SERVIÇO DE CONSERVAÇÃO DE ROTINA - SC.9",

    "36.767 - SERVIÇO DE CONSTRUÇÃO - ST.9",

    "36.768 - SERVIÇO DE PLANEJAMENTO E PROJETOS - SP.9",
]

# ==========================================================
# MAPAS DE NORMALIZAÇÃO
# ==========================================================
#
# Utilizados durante importação de planilhas e validação
# de dados para padronizar informações recebidas.

def criar_mapa(opcoes):
    return {opcao.strip().upper(): opcao for opcao in opcoes}

MAP_VINCULO = criar_mapa(OPCOES_VINCULO)
MAP_TIPO = criar_mapa(OPCOES_TIPO)
MAP_SUBTIPO_VINCULO = criar_mapa(OPCOES_SUBTIPO_VINCULO)
MAP_FORMA_INGRESSO = criar_mapa(OPCOES_FORMA_INGRESSO)
MAP_SITUACAO = criar_mapa(OPCOES_SITUACAO)
MAP_COORDENADORIA = criar_mapa(OPCOES_COORDENADORIA)
MAP_AREA = criar_mapa(OPCOES_AREA)
MAP_LOTACAO = criar_mapa(OPCOES_LOTACAO)

# ==========================================================
# STATUS
# ==========================================================

STATUS_ATIVO = 'Ativo'
STATUS_INATIVO_EXONERACAO = 'Inativo - Exoneração'
STATUS_INATIVO_DEMISSAO = 'Inativo - Demissão'
STATUS_INATIVO_APOSENTADORIA = 'Inativo - Aposentadoria'
STATUS_INATIVO_TERMINO_CONTRATO = 'Inativo - Término de contrato'
STATUS_INATIVO_OUTROS = 'Inativo - Outros'

STATUS_INATIVOS = {
    STATUS_INATIVO_EXONERACAO,
    STATUS_INATIVO_DEMISSAO,
    STATUS_INATIVO_APOSENTADORIA,
    STATUS_INATIVO_TERMINO_CONTRATO,
    STATUS_INATIVO_OUTROS,
}
