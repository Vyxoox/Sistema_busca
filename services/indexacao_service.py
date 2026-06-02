from datetime import datetime, date

from whoosh.query import Every

from models import Funcionario
from services.normalizacao_service import (
    normalizar_cpf,
    normalizar_rg,
    normalizar_maiusculo,
    normalizar_titulo,
)

def normalizar_titulo_simples(valor):
    if valor is None:
        return ''
    s = str(valor).strip()
    if not s or s.lower() in ('none', 'nan', 'nat'):
        return ''
    return ' '.join(p.capitalize() for p in s.split())

def date_to_datetime(val):
    if val is None:
        return None
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    return val

def reindexar_funcionario(ix, funcionario):
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
            preposto=normalizar_titulo(funcionario.preposto or ''),
        )

    writer.commit()

def reindexar_todos(ix):
    writer = ix.writer()
    writer.delete_by_query(Every())

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
            preposto=normalizar_titulo(func.preposto or ''),
        )

    writer.commit()
