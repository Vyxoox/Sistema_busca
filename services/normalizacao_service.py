import re

siglas_preservar = {'DER','CGR','UA','U.A','SEI','SP','SMA','D.E.R'}

def normalizar_cpf(valor):
    if valor is None:
        return ''
    s = str(valor).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return re.sub(r'\D', '', s)

def normalizar_rg(valor):
    if valor is None:
        return ''
    return re.sub(r'[^0-9A-Za-z]', '', str(valor)).upper()

def normalizar_maiusculo(valor):
    if valor is None:
        return ''
    s = str(valor).strip()
    if s.lower() == 'none':
        return ''
    return s.upper()

def normalizar_titulo(valor):
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
            parte_up = parte.upper()
            if parte_up in siglas_preservar or re.search(r'[0-9.]', parte):
                nova.append(parte_up)
            else:
                nova.append(parte.capitalize())
        saida.append(''.join(nova))
    return ' '.join(saida)

def escape_whoosh_query(s: str) -> str:
    if s is None:
        return ''
    s = str(s)
    s = s.replace("\\", "\\\\")
    for ch in ['+', '-', '!', '(', ')', '{', '}', '[', ']', '^', '"', '~', '*', '?', ':', '/', '&', '|']:
        s = s.replace(ch, f"\\{ch}")
    return s

def normalizar_situacao(valor):
    if not valor:
        return 'Ativo'
    s = str(valor).upper()
    if 'EXONER' in s:
        return 'Inativo - Exoneração'
    elif 'DEMIS' in s:
        return 'Inativo - Demissão'
    elif 'APOSENT' in s:
        return 'Inativo - Aposentadoria'
    elif 'TERMIN' in s or 'CONTRAT' in s:
        return 'Inativo - Término de contrato'
    elif 'INATIVO' in s:
        return 'Inativo - Outros'
    return 'Ativo'

def normalizar_forma_ingresso(valor):
    if not valor:
        return None
    s = str(valor).upper()
    if 'CONCURSO' in s:
        return 'Concurso Público'
    elif '500' in s:
        return 'Lei 500/74'
    elif 'LIVRE' in s or 'PROVIMENTO' in s:
        return 'Livre Provimento'
    elif 'OPT' in s or 'SUBSID' in s:
        return 'Optou 100% Subsídio'
    elif 'PRESTADOR' in s or 'SERVI' in s:
        return 'Prestador de Serviço'
    elif 'PROCESSO' in s or 'SELET' in s:
        return 'Processo Seletivo'
    return valor

def normalizar_vinculo(valor):
    if not valor:
        return None
    s = str(valor).upper()
    if 'SERV' in s:
        return 'SERVIDOR'
    elif 'TERC' in s:
        return 'TERCEIRIZADO'
    return valor

def normalizar_tipo(valor):
    if not valor:
        return None
    s = str(valor).upper()
    if 'EFET' in s:
        return 'EFETIVO'
    elif 'ESTAB' in s:
        return 'CELETISTA ESTÁVEL'
    elif 'CEL' in s:
        return 'CELETISTA'
    elif 'COMIS' in s:
        return 'COMISSIONADO'
    elif 'TERC' in s:
        return 'TERCEIRIZADO'
    return valor

def normalizar_subtipo_vinculo(valor):
    if not valor:
        return None
    s = str(valor).upper()
    if 'ADM' in s:
        return 'ADMINISTRATIVO'
    elif 'OPER' in s:
        return 'OPERACIONAL'
    return valor

def normalizar_coordenadoria(valor):
    if not valor:
        return None
    s = str(valor).upper()
    if '38.842' in s or 'CGR.9' in s or 'GERAL REGIONAL' in s:
        return '38.842 - COORDENADORIA GERAL REGIONAL - CGR.9'
    elif '38.844' in s or 'CA.9' in s or 'ADMINISTRATIVA' in s:
        return '38.844 - COORDENADORIA ADMINISTRATIVA - CA.9'
    elif '38.886' in s or 'CO.9' in s or 'CONSERV' in s:
        return '38.886 - COORDENADORIA DE CONSERVAÇÃO E OPERAÇÕES VIÁRIAS - CO.9'
    elif '38.922' in s or 'CT.9' in s or 'TECNICA' in s or 'TÉCNICA' in s:
        return '38.922 - COORDENADORIA TÉCNICA - CT.9'
    return valor

def normalizar_area_lotacao(valor, opcoes):
    if not valor:
        return None
    s = str(valor).upper().strip()
    
    # Extrai o código numérico inicial, se houver (ex: '38.846')
    match = re.match(r'^(\d{2}\.\d{3})', s)
    if match:
        codigo = match.group(1)
        for opcao in opcoes:
            if codigo in opcao:
                return opcao

    # Fallback por palavra-chave se não tiver código
    for opcao in opcoes:
        # Limpa acentos e compara
        opcao_clean = re.sub(r'[^A-Z0-9]', '', opcao.upper())
        val_clean = re.sub(r'[^A-Z0-9]', '', s)
        if val_clean in opcao_clean or opcao_clean in val_clean:
            return opcao
            
    return valor

