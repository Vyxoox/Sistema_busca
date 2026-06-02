
from services.normalizacao_service import normalizar_cpf, normalizar_rg

def formatar_cpf(cpf):
    cpf = normalizar_cpf(cpf)
    if not cpf or len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

def formatar_rg(rg):
    rg = normalizar_rg(rg)
    if not rg or len(rg) < 7:
        return rg
    if len(rg) == 9:
        return f"{rg[:2]}.{rg[2:5]}.{rg[5:8]}-{rg[8:]}"
    return rg
