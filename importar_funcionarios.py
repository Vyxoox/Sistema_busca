import pandas as pd
import re
from app import app
from core.extensions import db
from models import Funcionario
from datetime import datetime
from services.indexacao_service import reindexar_todos


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
        sheet_name=ABA
    )
    print(df.columns.tolist())

    print(f"{len(df)} registros encontrados")

    print("Apagando funcionários atuais...")

    Funcionario.query.delete()
    db.session.commit()

    contador = 0

    for _, linha in df.iterrows():
        funcionario = Funcionario(
            nome_completo=limpar_campo(linha['NOME COMPLETO']),
            cpf=normalizar_cpf(linha['CPF']),
            rg=normalizar_rg(linha['RG']),
            cin=limpar_campo(linha['CIN']),
            titulo_eleitor=limpar_campo(linha['TÍTULO DE ELEITOR']),
            pis_pasep=limpar_campo(linha['PIS/PASEP']),

            data_nasc=converter_data(linha['DATA DE NASCIMENTO']),
            endereco_residencial=limpar_campo(linha['ENDEREÇO RESIDENCIAL']),
            telefone_pessoal=limpar_campo(linha['TELEFONE PESSOAL']),
            email_pessoal=limpar_campo(linha['EMAIL PESSOAL']),

            email_institucional=limpar_campo(linha['EMAIL INSTITUCIONAL']),
            ramal=limpar_campo(linha['RAMAL(173218)']),

            vinculo=limpar_campo(linha['VÍNCULO']),
            tipo=limpar_campo(linha['TIPO']),
            subtipo_vinculo=limpar_campo(linha['SUBTIPO VÍNCULO']),
            forma_ingresso=limpar_campo(linha['FORMA DE INGRESSO']),
            prontuario_funcional=limpar_campo(linha['PRONTUÁRIO FUNCIONAL']),
            matricula=limpar_campo(linha['MATRÍCULA']),

            cargo_exercicio=limpar_campo(linha['CARGO EM EXERCÍCIO']),
            cargo_origem=limpar_campo(linha['CARGO DE ORIGEM']),

            lotacao=limpar_campo(linha['LOTAÇÃO ']),
            area=limpar_campo(linha['ÁREA DE ATUAÇÃO']),
            coordenadoria=limpar_campo(linha['COORDENADORIA']),

            data_ingresso_der=converter_data(linha['INGRESSO NO DER']),
            data_inicio=converter_data(linha['DATA INÍCIO']),
            data_admissao=converter_data(linha['DATA ADMISSÃO']),
            data_desligamento=converter_data(linha['DATA DESLIGAMENTO']),

            situacao=limpar_campo(linha['SITUAÇÃO']),

            doe_portaria=limpar_campo(linha['DOE / PORTARIA']),

            empresa_contratada=limpar_campo(linha['EMPRESA CONTRATADA']),
            numero_contrato=limpar_campo(linha['NÚMERO DO CONTRATO']),
            gestor_contrato=limpar_campo(linha['GESTOR DO CONTRATO']),
            fiscal_tecnico=limpar_campo(linha['FISCAL TÉCNICO']),
            fiscal_administrativo=limpar_campo(linha['FISCAL ADMINISTRATIVO']),
            preposto=limpar_campo(linha['PREPOSTO']),

            ativo=True
        )

        db.session.add(funcionario)

        contador += 1

    print("Salvando banco de dados...")
    db.session.commit()
    print(f"{contador} funcionários importados.")

    print("Reindexando Whoosh...")
    reindexar_todos(app.config['WHOOSH_IX'])
    print("Importação concluída.")

