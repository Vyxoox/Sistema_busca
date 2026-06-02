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
