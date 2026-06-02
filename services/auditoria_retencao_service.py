from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any

from sqlalchemy import and_, or_

from core.extensions import db
from models import LogAuditoria

# Importacao movida para dentro da funcao para evitar circularidade
# from services.auditoria_services import registrar_evento_seguro

def _agora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

def _normalizar_agora(agora_utc: datetime | None) -> datetime:
    if agora_utc is None:
        return _agora_utc_naive()
    if agora_utc.tzinfo is not None:
        return agora_utc.astimezone(UTC).replace(tzinfo=None)
    return agora_utc

def _consulta_expurgo(
    *,
    dias_geral: int,
    dias_seguranca: int,
    dias_alerta: int,
    agora_utc: datetime,
):
    corte_geral = agora_utc - timedelta(days=max(int(dias_geral), 1))
    corte_seguranca = agora_utc - timedelta(days=max(int(dias_seguranca), 1))
    corte_alerta = agora_utc - timedelta(days=max(int(dias_alerta), 1))

    return LogAuditoria.query.filter(
        or_(
            and_(LogAuditoria.categoria == 'alerta', LogAuditoria.criado_em < corte_alerta),
            and_(LogAuditoria.categoria == 'seguranca', LogAuditoria.criado_em < corte_seguranca),
            and_(LogAuditoria.categoria.notin_(('seguranca', 'alerta')), LogAuditoria.criado_em < corte_geral),
        )
    ), corte_geral, corte_seguranca, corte_alerta

def expurgar_logs_auditoria(
    *,
    dias_geral: int,
    dias_seguranca: int,
    dias_alerta: int,
    dry_run: bool = True,
    agora_utc: datetime | None = None,
) -> dict[str, Any]:
    agora = _normalizar_agora(agora_utc)

    consulta, corte_geral, corte_seguranca, corte_alerta = _consulta_expurgo(
        dias_geral =dias_geral,
        dias_seguranca=dias_seguranca,
        dias_alerta=dias_alerta,
        agora_utc=agora,
    )

    elegiveis = consulta.count()
    apagados = 0

    if not dry_run and elegiveis > 0:
        try:
            apagados = consulta.delete(synchronize_session=False)
            db.session.commit()

            from services.auditoria_services import registrar_evento_seguro
            registrar_evento_seguro(
                'AUDITORIA_EXPURGO_EXECUTADO',
                categoria='seguranca',
                recurso ='auditoria',
                detalhes={
                    'apagados': int(apagados),
                    'corte_geral': corte_geral.isoformat(),
                    'corte_seguranca': corte_seguranca.isoformat(),
                    'corte_alerta': corte_alerta.isoformat(),
                },
            )
        except Exception:
            db.session.rollback()
            raise

    return{
        'dry_run': dry_run,
        'elegiveis': int(elegiveis),
        'apagados': int(apagados),
        'corte_geral_utc': corte_geral.isoformat(),
        'corte_seguranca_utc': corte_seguranca.isoformat(),
        'corte_alerta_utc': corte_alerta.isoformat(),
    }
