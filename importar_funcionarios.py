import pandas as pd
import re
from app import app
from core.extensions import db
from models import Funcionario
from datetime import datetime
from services.normalizacao_service import (
    normalizar_maiusculo,
    normalizar_situacao,
    normalizar_forma_ingresso,
    normalizar_vinculo,
    normalizar_tipo,
    normalizar_subtipo_vinculo,
    normalizar_coordenadoria,
    normalizar_area_lotacao
)
from services.indexacao_service import reindexar_todos
from core.constante import OPCOES_AREA, OPCOES_LOTACAO


CAMINHO_PLANILHA = "dados/funcionarios.xlsx"
ABA = "FUNCIONARIOS"

###############################################
##############Funções Auxiliares###############
###############################################

def converter_data(valor):
    if pd.isna(valor):
        return None

    texto = str(valor).strip().lower()

    if texto in ("", "não se aplica", "nao se aplica"):
        return None

    if isinstance(valor, pd.Timestamp):
        return valor.date()

    try:
        return pd.to_datetime(valor).date()
    except:
        return None

def normalizar_cpf(valor):
    if pd.isna(valor):
        return None

    return re.sub(r'\D', '', str(valor))

def normalizar_rg(valor):
    if pd.isna(valor):
        return None

    return re.sub(r'[^0-9A-Za-z]', '', str(valor)).upper()

def limpar_campo(valor):
    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    if texto.lower() in ("não se aplica", "nao se aplica", ""):
        return None

    return texto

with app.app_context():

    print("Lendo planilha...")

    df = pd.read_excel(
        CAMINHO_PLANILHA,
        sheet_name=ABA,
        converters={
            "CPF": str,
            "RG": str,
            "CIN": str,
            "MATRÍCULA": str,
            "TÍTULO DE ELEITOR": str,
            "PIS/PASEP": str,
            "RAMAL(173218)": str,
            "PRONTUÁRIO FUNCIONAL": str,
            "NÚMERO DO CONTRATO": str
        }
    )
    print(df.columns.tolist())

    print(f"{len(df)} registros encontrados")

    print("Apagando funcionários atuais...")

    Funcionario.query.delete()
    db.session.commit()

    contador = 0

    for _, linha in df.iterrows():
        func_situacao = normalizar_situacao(linha.get("SITUAÇÃO"))
        funcionario = Funcionario(
            vinculo=normalizar_vinculo(linha.get("VÍNCULO")),
            tipo = normalizar_tipo(linha.get("TIPO")),
            subtipo_vinculo = normalizar_subtipo_vinculo(linha.get("SUBTIPO VÍNCULO")),
            forma_ingresso = normalizar_forma_ingresso(linha.get("FORMA DE INGRESSO")),
            situacao = func_situacao,
            ativo=(normalizar_maiusculo(func_situacao or '') == 'ATIVO'),
            nome_completo=limpar_campo(linha.get('NOME COMPLETO')),
            cpf=normalizar_cpf(linha.get('CPF')),
            rg=normalizar_rg(linha.get('RG')),
            cin=limpar_campo(linha.get('CIN')),
            titulo_eleitor=limpar_campo(linha.get('TÍTULO DE ELEITOR')),
            pis_pasep=limpar_campo(linha.get('PIS/PASEP')),

            data_nasc=converter_data(linha.get('DATA DE NASCIMENTO')),
            endereco_residencial=limpar_campo(linha.get('ENDEREÇO RESIDENCIAL')),
            telefone_pessoal=limpar_campo(linha.get('TELEFONE PESSOAL')),
            contato_emergencia=limpar_campo(linha.get('CONTATO DE EMERGÊNCIA')),
            email_pessoal=limpar_campo(linha.get('EMAIL PESSOAL')),

            email_institucional=limpar_campo(linha.get('EMAIL INSTITUCIONAL')),
            ramal=limpar_campo(linha.get('RAMAL(173218)')),

            prontuario_funcional=limpar_campo(linha.get('PRONTUÁRIO FUNCIONAL')),
            matricula=limpar_campo(linha.get('MATRÍCULA')),

            cargo_exercicio=limpar_campo(linha.get('CARGO EM EXERCÍCIO')),
            cargo_origem=limpar_campo(linha.get('CARGO DE ORIGEM')),

            lotacao=normalizar_area_lotacao(linha.get("LOTAÇÃO "), OPCOES_LOTACAO),
            area = normalizar_area_lotacao(linha.get("ÁREA DE ATUAÇÃO"), OPCOES_AREA),
            coordenadoria = normalizar_coordenadoria(linha.get("COORDENADORIA")),

            data_ingresso_der=converter_data(linha.get('INGRESSO NO DER')),
            data_inicio=converter_data(linha.get('DATA INÍCIO')),
            data_admissao=converter_data(linha.get('DATA ADMISSÃO')),
            data_desligamento=converter_data(linha.get('DATA DESLIGAMENTO')),

            doe_portaria=limpar_campo(linha.get('DOE / PORTARIA')),

            empresa_contratada=limpar_campo(linha.get('EMPRESA CONTRATADA')),
            numero_contrato=limpar_campo(linha.get('NÚMERO DO CONTRATO')),
            gestor_contrato=limpar_campo(linha.get('GESTOR DO CONTRATO')),
            fiscal_tecnico=limpar_campo(linha.get('FISCAL TÉCNICO')),
            fiscal_administrativo=limpar_campo(linha.get('FISCAL ADMINISTRATIVO')),
            preposto=limpar_campo(linha.get('PREPOSTO')),
        )

        db.session.add(funcionario)

        contador += 1

    print("Salvando banco de dados...")
    db.session.commit()
    print(f"{contador} funcionários importados.")

    print("Reindexando Whoosh...")
    reindexar_todos(app.config['WHOOSH_IX'])
    print("Importação concluída.")


