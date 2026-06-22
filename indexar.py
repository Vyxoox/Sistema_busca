import os
import shutil
import pandas as pd
from whoosh.index import create_in
from core.schema import schema
from datetime import datetime

# ============================================
# CONFIGURAÇÕES
# ============================================
CAMINHO_SERVIDORES = "dados/servidores.xlsx"
CAMINHO_TERCEIRIZADOS = "dados/terceirizados.xlsx"
CAMINHO_INDICE = "indice_funcionarios"


import re

def normalizar_cpf(valor):
    """CPF: mantém apenas dígitos (não completa com zeros à esquerda)."""
    if valor is None:
        return ''

    s = str(valor).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]

    return re.sub(r'\D', '', s)


def normalizar_rg(valor):
    """RG: mantém dígitos e letras (ex: 'X'), removendo pontuação e espaços."""
    if valor is None:
        return ''
    return re.sub(r'[^0-9A-Za-z]', '', str(valor)).upper()


SIGLAS_PRESERVAR = {
    'DER', 'CGR', 'UA', 'U.A', 'SEI', 'SP', 'SMA'
}


def normalizar_titulo(valor):
    """Texto: primeira letra de cada palavra em maiúsculo, preservando siglas."""
    if valor is None:
        return ''
    s = str(valor).strip()
    if not s:
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
            parte_up = parte.upper()
            if parte_up in SIGLAS_PRESERVAR or re.search(r'[0-9.]', parte):
                nova.append(parte_up)
            else:
                nova.append(parte.capitalize())
        saida.append(''.join(nova))
    return ' '.join(saida)


def normalizar_titulo_simples(valor):
    """Texto: primeira letra de cada palavra em maiúsculo (sem preservar siglas)."""
    if valor is None:
        return ''
    s = str(valor).strip()
    if not s:
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


def normalizar_maiusculo(valor):
    """Texto: tudo em maiúsculo."""
    if valor is None:
        return ''
    return str(valor).strip().upper()


# Backward-compat: função antiga (apenas dígitos). Mantida para usos residuais.
def normalizar_documento(valor):
    return normalizar_cpf(valor)

# ============================================
# FUNÇÃO AUXILIAR PARA CONVERTER DATAS (CORRIGIDA)
# ============================================
def converter_data(valor):
    """Converte valor para datetime nativo do Python."""
    if pd.isna(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()  # Converte para datetime do Python
    if isinstance(valor, datetime):
        return valor
    # Se for string, tenta converter
    try:
        # Formato dd/mm/aaaa
        return datetime.strptime(str(valor).strip(), "%d/%m/%Y")
    except:
        try:
            # Formato aaaa-mm-dd (ISO)
            return datetime.strptime(str(valor).strip(), "%Y-%m-%d")
        except:
            print(f"⚠️ Data não reconhecida: {valor} (ignorada)")
            return None


# ============================================
# CRIA ÍNDICE (APAGA SE JÁ EXISTIR)
# ============================================
if os.path.exists(CAMINHO_INDICE):
    shutil.rmtree(CAMINHO_INDICE)
    print(f"🗑️ Índice antigo removido: {CAMINHO_INDICE}")
os.mkdir(CAMINHO_INDICE)
ix = create_in(CAMINHO_INDICE, schema)
print("✅ Índice criado com sucesso!")

writer = ix.writer()

# ============================================
# INDEXAR SERVIDORES (aba SERVIDORES)
# ============================================
print("\n📄 Lendo planilha de servidores (aba 'SERVIDORES')...")
try:
    # Força CPF/RG como texto para não perder zeros à esquerda na leitura do Excel.
    df_servidores = pd.read_excel(
        CAMINHO_SERVIDORES,
        sheet_name="SERVIDORES",
        converters={"CPF": str, "RG": str}
    )
    df_servidores.columns = (
        df_servidores.columns
        .str.strip()
        .str.upper()
        .str.normalize('NFKD')
        .str.encode('ascii', errors='ignore')
        .str.decode('utf-8')
    )
    print(f"   {len(df_servidores)} registros encontrados.")

    id_global = 1
    contador = 0
    for idx, linha in df_servidores.iterrows():
        try:
            doc = {
                'id': str(id_global),
                'matricula': str(linha['MATRICULA']) if pd.notna(linha['MATRICULA']) else '',
                'cpf': normalizar_cpf(linha['CPF']),
                'rg': normalizar_rg(linha['RG']),
                'cin': str(linha['CIN']) if pd.notna(linha['CIN']) else '',
                'titulo_eleitor': str(linha['TITULO DE ELEITOR']) if pd.notna(linha['TITULO DE ELEITOR']) else '',
                'pis_pasep': str(linha['PIS/PASEP']) if pd.notna(linha['PIS/PASEP']) else '',

                'nome_completo': normalizar_titulo(linha['NOME COMPLETO']) if pd.notna(linha['NOME COMPLETO']) else '',
                'data_nasc': converter_data(linha['DATA DE NASCIMENTO']),
                'endereco_residencial': str(linha['ENDERECO RESIDENCIAL']) if pd.notna(linha['ENDERECO RESIDENCIAL']) else '',
                'telefone_pessoal': str(linha['TELEFONE PESSOAL']) if pd.notna(linha['TELEFONE PESSOAL']) else '',
                'email_pessoal': str(linha['EMAIL PESSOAL']) if pd.notna(linha['EMAIL PESSOAL']) else '',
                'email_institucional': str(linha['EMAIL INSTITUCIONAL']) if pd.notna(linha['EMAIL INSTITUCIONAL']) else '',
                'ramal': str(linha['RAMAL(173218)']) if pd.notna(linha['RAMAL(173218)']) else '',

                'vinculo': normalizar_maiusculo(linha['VINCULO']),
                'tipo': normalizar_maiusculo(linha['TIPO']) if pd.notna(linha['TIPO']) else '',
                'subtipo_vinculo': normalizar_maiusculo(linha['SUBTIPO VINCULO']) if pd.notna(linha['SUBTIPO VINCULO']) else '',
                'forma_ingresso': normalizar_titulo(linha['FORMA DE INGRESSO']) if pd.notna(linha['FORMA DE INGRESSO']) else '',
                'prontuario_funcional': str(linha['PRONTUARIO FUNCIONAL']) if pd.notna(linha['PRONTUARIO FUNCIONAL']) else '',

                'cargo_exercicio': normalizar_titulo(linha['CARGO EM EXERCICIO']) if pd.notna(linha['CARGO EM EXERCICIO']) else '',
                'cargo_origem': normalizar_titulo(linha['CARGO DE ORIGEM']) if pd.notna(linha['CARGO DE ORIGEM']) else '',

                'lotacao': normalizar_titulo_simples(linha['LOTACAO']) if pd.notna(linha['LOTACAO']) else '',
                'area': normalizar_titulo(linha['AREA DE ATUACAO']) if pd.notna(linha['AREA DE ATUACAO']) else '',
                'coordenadoria': normalizar_maiusculo(linha['COORDENADORIA']) if pd.notna(linha['COORDENADORIA']) else '',

                'data_ingresso_der': converter_data(linha['INGRESSO NO DER']),
                'data_inicio': converter_data(linha['DATA INICIO']),
                'data_admissao': converter_data(linha['DATA ADMISSAO']),
                'data_desligamento': converter_data(linha['DATA DESLIGAMENTO']),

                'situacao': str(linha['SITUACAO']) if pd.notna(linha['SITUACAO']) else 'Ativo',
                'ativo': (str(linha['SITUACAO']).strip().upper() == 'ATIVO' if pd.notna(linha['SITUACAO']) else True),

                'doe_portaria': str(linha['DOE / PORTARIA']) if pd.notna(linha['DOE / PORTARIA']) else '',

                'empresa_contratada': str(linha['EMPRESA CONTRATADA']) if pd.notna(linha['EMPRESA CONTRATADA']) else '',
                'numero_contrato': str(linha['NUMERO DO CONTRATO']) if pd.notna(linha['NUMERO DO CONTRATO']) else '',
                'gestor_contrato': str(linha['GESTOR DO CONTRATO']) if pd.notna(linha['GESTOR DO CONTRATO']) else '',
                'fiscal_tecnico': str(linha['FISCAL TECNICO']) if pd.notna(linha['FISCAL TECNICO']) else '',
                'fiscal_administrativo': str(linha['FISCAL ADMINISTRATIVO']) if pd.notna(linha['FISCAL ADMINISTRATIVO']) else '',
                'preposto': str(linha['PREPOSTO']) if pd.notna(linha['PREPOSTO']) else '',
            }
            writer.add_document(**doc)
            contador += 1
            id_global += 1
            if contador % 50 == 0:
                print(f"   ... {contador} servidores indexados")
        except Exception as e:
            print(f"❌ Erro ao indexar servidor linha {idx}: {e}")
            print("Linha:", linha.to_dict())
            raise  # Interrompe a execução para que o erro seja corrigido
    print(f"   ✅ {contador} servidores indexados.")
except Exception as e:
    print(f"❌ Erro ao ler servidores: {e}")
    raise

# ============================================
# INDEXAR TERCEIRIZADOS (aba TERCEIROS)
# ============================================
print("\n📄 Lendo planilha de terceirizados (aba 'TERCEIROS')...")
try:
    df_terceirizados = pd.read_excel(
        CAMINHO_TERCEIRIZADOS,
        sheet_name="TERCEIROS",
        converters={"CPF": str, "SEI": str}
    )
    df_terceirizados.columns = (
        df_terceirizados.columns
        .str.strip()
        .str.upper()
        .str.normalize('NFKD')
        .str.encode('ascii', errors='ignore')
        .str.decode('utf-8')
    )
    print(f"   {len(df_terceirizados)} registros encontrados.")

    contador = 0
    for idx, linha in df_terceirizados.iterrows():
        try:
            doc = {
                'id': str(id_global),
                'matricula': str(linha['MATRICULA']) if pd.notna(linha['MATRICULA']) else '',
                'cpf': normalizar_cpf(linha['CPF']),
                'rg': normalizar_rg(linha['RG']),
                'cin': str(linha['CIN']) if pd.notna(linha['CIN']) else '',
                'titulo_eleitor': str(linha['TITULO DE ELEITOR']) if pd.notna(linha['TITULO DE ELEITOR']) else '',
                'pis_pasep': str(linha['PIS/PASEP']) if pd.notna(linha['PIS/PASEP']) else '',

                'nome_completo': normalizar_titulo(linha['NOME COMPLETO']) if pd.notna(linha['NOME COMPLETO']) else '',
                'data_nasc': converter_data(linha['DATA DE NASCIMENTO']),
                'endereco_residencial': str(linha['ENDERECO RESIDENCIAL']) if pd.notna(linha['ENDERECO RESIDENCIAL']) else '',
                'telefone_pessoal': str(linha['TELEFONE PESSOAL']) if pd.notna(linha['TELEFONE PESSOAL']) else '',
                'email_pessoal': str(linha['EMAIL PESSOAL']) if pd.notna(linha['EMAIL PESSOAL']) else '',
                'email_institucional': str(linha['EMAIL INSTITUCIONAL']) if pd.notna(linha['EMAIL INSTITUCIONAL']) else '',
                'ramal': str(linha['RAMAL(173218)']) if pd.notna(linha['RAMAL(173218)']) else '',

                'vinculo': normalizar_maiusculo(linha['VINCULO']),
                'tipo': normalizar_maiusculo(linha['TIPO']) if pd.notna(linha['TIPO']) else '',
                'subtipo_vinculo': normalizar_maiusculo(linha['SUBTIPO VINCULO']) if pd.notna(linha['SUBTIPO VINCULO']) else '',
                'forma_ingresso': normalizar_titulo(linha['FORMA DE INGRESSO']) if pd.notna(linha['FORMA DE INGRESSO']) else '',
                'prontuario_funcional': str(linha['PRONTUARIO FUNCIONAL']) if pd.notna(linha['PRONTUARIO FUNCIONAL']) else '',

                'cargo_exercicio': normalizar_titulo(linha['CARGO EM EXERCICIO']) if pd.notna(linha['CARGO EM EXERCICIO']) else '',
                'cargo_origem': normalizar_titulo(linha['CARGO DE ORIGEM']) if pd.notna(linha['CARGO DE ORIGEM']) else '',

                'lotacao': normalizar_titulo_simples(linha['LOTACAO']) if pd.notna(linha['LOTACAO']) else '',
                'area': normalizar_titulo(linha['AREA DE ATUACAO']) if pd.notna(linha['AREA DE ATUACAO']) else '',
                'coordenadoria': normalizar_maiusculo(linha['COORDENADORIA']) if pd.notna(linha['COORDENADORIA']) else '',

                'data_ingresso_der': converter_data(linha['INGRESSO NO DER']),
                'data_inicio': converter_data(linha['DATA INICIO']),
                'data_admissao': converter_data(linha['DATA ADMISSAO']),
                'data_desligamento': converter_data(linha['DATA DESLIGAMENTO']),

                'situacao': str(linha['SITUACAO']) if pd.notna(linha['SITUACAO']) else 'Ativo',
                'ativo': (str(linha['SITUACAO']).strip().upper() == 'ATIVO' if pd.notna(linha['SITUACAO']) else True),

                'doe_portaria': str(linha['DOE / PORTARIA']) if pd.notna(linha['DOE / PORTARIA']) else '',

                'empresa_contratada': str(linha['EMPRESA CONTRATADA']) if pd.notna(linha['EMPRESA CONTRATADA']) else '',
                'numero_contrato': str(linha['NUMERO DO CONTRATO']) if pd.notna(linha['NUMERO DO CONTRATO']) else '',
                'gestor_contrato': str(linha['GESTOR DO CONTRATO']) if pd.notna(linha['GESTOR DO CONTRATO']) else '',
                'fiscal_tecnico': str(linha['FISCAL TECNICO']) if pd.notna(linha['FISCAL TECNICO']) else '',
                'fiscal_administrativo': str(linha['FISCAL ADMINISTRATIVO']) if pd.notna(linha['FISCAL ADMINISTRATIVO']) else '',
                'preposto': str(linha['PREPOSTO']) if pd.notna(linha['PREPOSTO']) else '',
            }
            writer.add_document(**doc)
            contador += 1
            id_global += 1
            if contador % 50 == 0:
                print(f"   ... {contador} terceirizados indexados")
        except Exception as e:
            print(f"❌ Erro ao indexar terceirizado linha {idx}: {e}")
            print("Linha:", linha.to_dict())
            raise  # Interrompe a execução
    print(f"   ✅ {contador} terceirizados indexados.")
except Exception as e:
    print(f"❌ Erro ao ler terceirizados: {e}")
    raise

# ============================================
# FINALIZAR
# ============================================
print("ANTES DO COMMIT")
print("INDEXAR CWD =", os.getcwd())
print("INDEXAR PATH =", os.path.abspath(CAMINHO_INDICE))
writer.commit()
from whoosh.index import open_dir

ix_test = open_dir(CAMINHO_INDICE)

with ix_test.searcher() as s:
    print("DOC_COUNT FINAL =", s.doc_count())
print("\n✅ Indexação concluída!")
