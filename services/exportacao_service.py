def valor_exportacao_resultado(resultado, campo):
    valor = resultado.get(campo, None)
    vinculo = str(resultado.get('vinculo', '')).upper()

    campos_so_servidor = {'matricula', 'cargo_origem', 'doe_portaria', 'data_inicio'}
    campos_so_terceirizado = {
        'data_admissao',
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

def limpar_valor_excel(val):
    if val is None:
        return ''

    if isinstance(val, str):
        val = val.strip()
        if val.lower() in ('none', 'nat') or val == '':
            return ''

    return val
