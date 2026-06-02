from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from services.auditoria_retencao_service import expurgar_logs_auditoria


def main() -> int:
    parser = argparse.ArgumentParser(description='Expurgo de logs de auditoria')
    parser.add_argument('--apply', action='store_true', help='Aplica o expurgo (Sem isso, roda em dry-run)')
    parser.add_argument('--dias-gerais', type=int, default=None)
    parser.add_argument('--dias-seguranca', type=int, default=None)
    parser.add_argument('--dias-alerta', type=int, default=None)
    args = parser.parse_args()

    with app.app_context():
        dias_gerais = args.dias_gerais or app.config.get('AUDIT_RETENCAO_DIAS_GERAL', 365)
        dias_seguranca = args.dias_seguranca or app.config.get('AUDIT_RETENCAO_DIAS_SEGURANCA', 1825)
        dias_alerta = args.dias_alerta or app.config.get('AUDIT_RETENCAO_DIAS_ALERTA', 3650)

        resultado = expurgar_logs_auditoria(
            dias_geral=dias_gerais,
            dias_seguranca=dias_seguranca,
            dias_alerta=dias_alerta,
            dry_run=not args.apply,
        )

    print(f"dry_run={resultado['dry_run']}")
    print(f"elegiveis={resultado['elegiveis']}")
    print(f"apagados={resultado['apagados']}")
    print(f"corte_geral={resultado['corte_geral_utc']}")
    print(f"corte_seguranca={resultado['corte_seguranca_utc']}")
    print(f"corte_alerta={resultado['corte_alerta_utc']}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
