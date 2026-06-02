from whoosh.fields import Schema, TEXT, KEYWORD, ID, DATETIME, BOOLEAN
from whoosh.analysis import StandardAnalyzer, CharsetFilter
from whoosh.support.charset import accent_map

# Analyzer com lowercasing e remoção de acentos
analisador = StandardAnalyzer() | CharsetFilter(accent_map)

schema = Schema(
    # ===== Identificadores =====
    id=ID(stored=True, unique=True),
    matricula=ID(stored=True),
    cpf=ID(stored=True),
    rg=ID(stored=True),
    cin=ID(stored=True),
    titulo_eleitor=ID(stored=True),
    pis_pasep=ID(stored=True),

    # ===== Dados pessoais =====
    nome_completo=TEXT(analyzer=analisador, stored=True),
    data_nasc=DATETIME(stored=True),
    endereco_residencial=TEXT(analyzer=analisador, stored=True),
    telefone_pessoal=ID(stored=True),
    email_pessoal=ID(stored=True),
    email_institucional=ID(stored=True),
    ramal=ID(stored=True),

    # ===== Vínculo =====
    vinculo=KEYWORD(stored=True),
    tipo=KEYWORD(stored=True),
    subtipo_vinculo=KEYWORD(stored=True),
    forma_ingresso=KEYWORD(stored=True),
    prontuario_funcional=ID(stored=True),

    # ===== Cargos =====
    cargo_exercicio=TEXT(analyzer=analisador, stored=True),
    cargo_origem=TEXT(analyzer=analisador, stored=True),

    # ===== Estrutura =====
    lotacao=TEXT(analyzer=analisador, stored=True),
    area=TEXT(analyzer=analisador, stored=True),
    coordenadoria=KEYWORD(stored=True),

    # ===== Datas =====
    data_ingresso_der=DATETIME(stored=True),
    data_inicio=DATETIME(stored=True),
    data_admissao=DATETIME(stored=True),
    data_desligamento=DATETIME(stored=True),

    # ===== Situação =====
    situacao=TEXT(analyzer=analisador, stored=True),
    ativo=BOOLEAN(stored=True),

    # ===== Documentos / publicação =====
    doe_portaria=TEXT(analyzer=analisador, stored=True),

    # ===== Contrato / terceirizados =====
    empresa_contratada=TEXT(analyzer=analisador, stored=True),
    numero_contrato=ID(stored=True),
    gestor_contrato=TEXT(analyzer=analisador, stored=True),
    fiscal_tecnico=TEXT(analyzer=analisador, stored=True),
    fiscal_administrativo=TEXT(analyzer=analisador, stored=True),
    preposto=TEXT(analyzer=analisador, stored=True)
)