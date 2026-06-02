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
                'cin': '',
                'titulo_eleitor': '',
                'pis_pasep': '',

                'nome_completo': normalizar_titulo(linha['NOME COMPLETO']) if pd.notna(linha['NOME COMPLETO']) else '',
                'data_nasc': converter_data(linha['DATA DE NASC']),
                'endereco_residencial': '',
                'telefone_pessoal': '',
                'email_pessoal': '',
                'email_institucional': 'email.sede@der.sp.gov.br',
                'ramal': '',

                'vinculo': 'SERVIDOR',
                'tipo': normalizar_maiusculo(linha['TIPO']) if pd.notna(linha['TIPO']) else '',
                'subtipo_vinculo': '',
                'forma_ingresso': normalizar_titulo(linha['FORMA']) if pd.notna(linha['FORMA']) else '',
                'prontuario_funcional': '',

                'cargo_exercicio': normalizar_titulo(linha['CARGO EM EXERCÍCIO']) if pd.notna(
                    linha['CARGO EM EXERCÍCIO']) else '',
                'cargo_origem': normalizar_titulo(linha['CARGO ORIGEM']) if pd.notna(linha['CARGO ORIGEM']) else '',

                'lotacao': normalizar_titulo_simples(
                    f"{linha['UA']} - {linha['U.A. CARGO ORIGEM']}"
                    if pd.notna(linha['UA']) and pd.notna(linha['U.A. CARGO ORIGEM'])
                    else str(linha['UA']) if pd.notna(linha['UA'])
                    else ''
                ),
                'area': normalizar_titulo(linha['AREA']) if pd.notna(linha['AREA']) else '',
                'coordenadoria': normalizar_maiusculo(linha['DIRETORIA']) if pd.notna(linha['DIRETORIA']) else '',

                'data_ingresso_der': converter_data(linha['ENTRADA NO DER']),
                'data_inicio': converter_data(linha['INICIO DE EXERCICIO']),
                'data_admissao': None,
                'data_desligamento': None,

                'situacao': 'Ativo',
                'ativo': True,

                'doe_portaria': str(linha['DOE / PORTARIA']) if pd.notna(linha['DOE / PORTARIA']) else '',

                'empresa_contratada': '',
                'numero_contrato': '',
                'gestor_contrato': '',
                'fiscal_tecnico': '',
                'fiscal_administrativo': '',
                'preposto': ''
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
    print(f"   {len(df_terceirizados)} registros encontrados.")

    contador = 0
    for idx, linha in df_terceirizados.iterrows():
        try:
            # Tratamento do subtipo (Administrativo/Operacional)
            subtipo = linha['Terceiro (Administrativo/Operacional)']
            if pd.notna(subtipo):
                subtipo = str(subtipo).strip().lower()
                if 'administrativo' in subtipo:
                    subtipo = 'ADMINISTRATIVO'
                elif 'operacional' in subtipo:
                    subtipo = 'OPERACIONAL'
                else:
                    subtipo = normalizar_maiusculo(subtipo)
            else:
                subtipo = ''
            doc = {
                'id': str(id_global),
                'matricula': '',
                'cpf': normalizar_cpf(linha['CPF']),
                'rg': '',
                'cin': '',
                'titulo_eleitor': '',
                'pis_pasep': '',

                'nome_completo': normalizar_titulo(linha['Nome']) if pd.notna(linha['Nome']) else '',
                'data_nasc': None,
                'endereco_residencial': '',
                'telefone_pessoal': '',
                'email_pessoal': '',
                'email_institucional': 'email.sede@der.sp.gov.br',
                'ramal': '',

                'vinculo': 'TERCEIRIZADO',
                'tipo': 'CELETISTA',
                'subtipo_vinculo': subtipo,

                'forma_ingresso': '',
                'prontuario_funcional': '',

                'cargo_exercicio': normalizar_titulo(linha['Cargo']) if pd.notna(linha['Cargo']) else '',
                'cargo_origem': '',

                'lotacao': '',
                'area': normalizar_titulo(linha['Area']) if pd.notna(linha['Area']) else '',
                'coordenadoria': normalizar_maiusculo(linha['Diretoria']) if pd.notna(linha['Diretoria']) else '',

                'data_ingresso_der': None,
                'data_inicio': None,
                'data_admissao': converter_data(linha['Admissão']),
                'data_desligamento': None,

                'situacao': 'Ativo',
                'ativo': True,

                'doe_portaria': '',

                'empresa_contratada': normalizar_titulo_simples(linha['Empresa']) if pd.notna(linha['Empresa']) else '',
                'numero_contrato': str(linha['SEI']) if pd.notna(linha['SEI']) else '',
                'gestor_contrato': '',
                'fiscal_tecnico': '',
                'fiscal_administrativo': '',
                'preposto': ''
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
writer.commit()
print("\n✅ Indexação concluída!")
