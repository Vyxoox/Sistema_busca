import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app
from core.extensions import db
from models import LogAuditoria


def main() -> int:
    ip = (sys.argv[1] if len(sys.argv) > 1 else '').strip()
    motivo = (sys.argv[2] if len(sys.argv) > 2 else 'desbloqueio_emergencial_manual').strip()

    if not ip:
        print('Uso: python scripts/unlock_ip_emergency.py <ip> [motivo]')
        return 1

    criado_em = datetime.now(UTC).replace(tzinfo=None)
    detalhes = {
        'ip_alvo': ip,
        'regra': 'desbloqueio_emergencial',
        'motivo': motivo,
    }

    with app.app_context():
        log = LogAuditoria(
            usuario_id=None,
            usuario_login=None,
            acao='SEC_DESBLOQUEIO_IP_LOGIN_MANUAL',
            categoria='seguranca',
            status='sucesso',
            recurso='autenticacao',
            recurso_id=ip,
            metodo_http=None,
            rota=None,
            ip_origem=ip,
            user_agent='script-emergencial',
            detalhes=json.dumps(detalhes, ensure_ascii=False),
            criado_em=criado_em,
        )
        db.session.add(log)
        db.session.commit()

    print(f'Desbloqueio criado: id={log.id}, ip={ip}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
