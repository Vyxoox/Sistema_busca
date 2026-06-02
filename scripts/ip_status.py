import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app
from models import LogAuditoria


def main() -> int:
    ip = (sys.argv[1] if len(sys.argv) > 1 else '').strip()
    if not ip:
        print('Uso: python scripts/ip_status.py <ip>')
        return 1

    with app.app_context():
        row = (
            LogAuditoria.query
            .filter(LogAuditoria.acao.in_(('SEC_BLOQUEIO_IP_LOGIN', 'SEC_DESBLOQUEIO_IP_LOGIN_MANUAL')))
            .filter(LogAuditoria.detalhes.like(f'%"ip_alvo": "{ip}"%'))
            .order_by(LogAuditoria.id.desc())
            .first()
        )

    if not row:
        print(f'IP {ip}: sem historico de bloqueio/desbloqueio')
        return 0

    try:
        detalhes = json.loads(row.detalhes or '{}')
    except Exception:
        detalhes = {'detalhes_brutos': row.detalhes}

    bloqueado = row.acao == 'SEC_BLOQUEIO_IP_LOGIN'
    print(f'IP: {ip}')
    print(f'Bloqueado agora: {"SIM" if bloqueado else "NAO"}')
    print(f'Ultimo evento: {row.acao} (id={row.id}, criado_em={row.criado_em})')
    print(f'Detalhes: {json.dumps(detalhes, ensure_ascii=False)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
