import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.config import settings
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission
from app.modules.merqry_sync.readonly_guard import (
    MerqryReadOnlyViolationError,
    assert_merqry_readonly_sql,
)

router = APIRouter(prefix="/api/v1/merqry", tags=["Merqry Read-Only & Circuitos (Fase 2)"])


class MerqrySnapshotItem(BaseModel):
    merqry_employee_id: str = Field(..., min_length=1, max_length=50)
    curp: Optional[str] = None
    nombre_completo: str = Field(..., min_length=2, max_length=180)
    puesto_nominal_merqry: Optional[str] = None
    estatus_merqry: str = "ALTA"
    salario_diario_imss: Optional[float] = None


class CargarSnapshotIn(BaseModel):
    empresa_id: int
    fuente_lectura: str = "MYSQL_READONLY_SNAPSHOT"
    registros: List[MerqrySnapshotItem] = Field(..., min_length=1)


class GenerarExportIn(BaseModel):
    empresa_id: int
    periodo_label: str = Field(..., min_length=3, max_length=40)


class ValidarConsultaIn(BaseModel):
    sql: str


@router.get("/status")
async def estado_conector_merqry(
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=2)),
):
    return {
        "integration_mode": "READ_ONLY" if settings.merqry_readonly_mode else "INVALID",
        "write_migrations_allowed": False,
        "mysql_mirror_configured": bool(settings.merqry_mysql_host),
        "circuitos_separados": ["IMSS_MERQRY -> Merqry", "ESPECIAL_CONTABILIDAD -> Contabilidad"],
    }


@router.post("/validate-readonly-sql")
async def validar_sql_solo_lectura(
    data: ValidarConsultaIn,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
):
    try:
        sanitized = assert_merqry_readonly_sql(data.sql)
    except MerqryReadOnlyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MERQRY_READONLY_VIOLATION", "message": str(exc)},
        ) from exc
    return {"allowed": True, "mode": "READ_ONLY", "sql": sanitized}


@router.post("/staging/cargar-snapshot", status_code=status.HTTP_201_CREATED)
async def cargar_snapshot_merqry(
    data: CargarSnapshotIn,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """Carga snapshot de SOLO LECTURA hacia merqry_staging_empleados en PostgreSQL local."""
    assert_scope(actor, "merqry.leer_conciliar", empresa_id=data.empresa_id, min_level=3)
    if not settings.merqry_readonly_mode:
        raise HTTPException(status_code=500, detail="MERQRY_READONLY_MODE inválido.")

    count = 0
    for item in data.registros:
        await db.execute(
            text(
                """
                INSERT INTO merqry_staging_empleados (
                    empresa_id, merqry_employee_id, curp, nombre_completo,
                    puesto_nominal_merqry, estatus_merqry, salario_diario_imss, fuente_lectura, sincronizado_en
                ) VALUES (
                    :emp, :mid, :curp, :nom, :puesto, :est, :sal, :fuente, NOW()
                )
                ON CONFLICT (empresa_id, merqry_employee_id) DO UPDATE SET
                    curp = EXCLUDED.curp,
                    nombre_completo = EXCLUDED.nombre_completo,
                    puesto_nominal_merqry = EXCLUDED.puesto_nominal_merqry,
                    estatus_merqry = EXCLUDED.estatus_merqry,
                    salario_diario_imss = EXCLUDED.salario_diario_imss,
                    fuente_lectura = EXCLUDED.fuente_lectura,
                    sincronizado_en = NOW()
                """
            ),
            {
                "emp": data.empresa_id,
                "mid": item.merqry_employee_id.strip(),
                "curp": item.curp.strip().upper() if item.curp else None,
                "nom": item.nombre_completo.strip(),
                "puesto": item.puesto_nominal_merqry,
                "est": item.estatus_merqry.strip().upper(),
                "sal": item.salario_diario_imss,
                "fuente": data.fuente_lectura,
            },
        )
        count += 1

    await registrar_auditoria(
        db,
        actor,
        modulo="merqry_sync",
        accion="CARGAR_SNAPSHOT_READONLY",
        tipo_entidad="MERQRY_STAGING",
        id_entidad=str(data.empresa_id),
        empresa_id=data.empresa_id,
        datos_despues={"registros_cargados": count, "fuente": data.fuente_lectura},
    )
    await db.commit()
    return {"empresa_id": data.empresa_id, "registros_cargados": count, "mode": "READ_ONLY"}


@router.get("/conciliacion")
async def conciliar_relaciones_vs_merqry(
    empresa_id: int = Query(...),
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """
    Concilia relaciones_laborales locales contra merqry_staging_empleados (solo lectura),
    separando estrictamente IMSS_MERQRY vs ESPECIAL_CONTABILIDAD.
    """
    assert_scope(actor, "merqry.leer_conciliar", empresa_id=empresa_id, min_level=3)

    rels = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT rl.id::text AS relacion_id, rl.numero_empleado, rl.merqry_employee_id,
                       rl.circuito_pago, rl.estatus, p.curp,
                       p.nombre || ' ' || p.apellido_paterno AS nombre_erp,
                       pu.titulo AS puesto_nominal_erp
                FROM relaciones_laborales rl
                JOIN personas p ON p.id = rl.persona_id
                JOIN puestos pu ON pu.id = rl.puesto_nominal_id
                WHERE rl.empresa_id = :emp AND rl.estatus <> 'BAJA'
                ORDER BY rl.numero_empleado
                """
            ),
            {"emp": empresa_id},
        )
    ]

    staging = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT merqry_employee_id, curp, nombre_completo, puesto_nominal_merqry, estatus_merqry
                FROM merqry_staging_empleados
                WHERE empresa_id = :emp
                ORDER BY merqry_employee_id
                """
            ),
            {"emp": empresa_id},
        )
    ]

    by_mid = {s["merqry_employee_id"]: s for s in staging}
    by_curp = {s["curp"]: s for s in staging if s["curp"]}
    matched_mids = set()

    conciliados: List[Dict[str, Any]] = []
    falta_en_merqry: List[Dict[str, Any]] = []
    excluidos_especial: List[Dict[str, Any]] = []

    for r in rels:
        if r["circuito_pago"] == "ESPECIAL_CONTABILIDAD":
            excluidos_especial.append(
                {
                    **r,
                    "estado_conciliacion": "EXCLUIDO_DE_MERQRY_CIRCUITO_ESPECIAL",
                    "destino": "CONTABILIDAD",
                }
            )
            continue

        match = by_mid.get(r["merqry_employee_id"]) or (by_curp.get(r["curp"]) if r["curp"] else None)
        if match:
            matched_mids.add(match["merqry_employee_id"])
            conciliados.append(
                {
                    **r,
                    "merqry_match_id": match["merqry_employee_id"],
                    "puesto_nominal_merqry": match["puesto_nominal_merqry"],
                    "estado_conciliacion": "CONCILIADO",
                }
            )
        else:
            falta_en_merqry.append({**r, "estado_conciliacion": "FALTA_EN_MERQRY"})

    falta_en_erp = [
        {**s, "estado_conciliacion": "FALTA_EN_ERP"}
        for s in staging
        if s["merqry_employee_id"] not in matched_mids
    ]

    return {
        "empresa_id": empresa_id,
        "merqry_mode": "READ_ONLY",
        "resumen": {
            "conciliados_imss": len(conciliados),
            "falta_en_merqry_imss": len(falta_en_merqry),
            "falta_en_erp": len(falta_en_erp),
            "excluidos_especial_contabilidad": len(excluidos_especial),
        },
        "conciliados": conciliados,
        "falta_en_merqry": falta_en_merqry,
        "falta_en_erp": falta_en_erp,
        "excluidos_especial": excluidos_especial,
    }


async def _generar_export_circuito(
    db: AsyncSession,
    actor: AuthenticatedActor,
    *,
    empresa_id: int,
    periodo_label: str,
    circuito_destino: str,
) -> Dict[str, Any]:
    assert_scope(actor, "merqry.leer_conciliar", empresa_id=empresa_id, min_level=3)

    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT
                    rl.numero_empleado,
                    rl.merqry_employee_id,
                    rl.circuito_pago,
                    p.curp,
                    p.nombre || ' ' || p.apellido_paterno AS nombre_completo,
                    pu.codigo_puesto AS puesto_nominal,
                    COALESCE(ep.estatus, 'ACTIVO') AS estatus_expediente
                FROM relaciones_laborales rl
                JOIN personas p ON p.id = rl.persona_id
                JOIN puestos pu ON pu.id = rl.puesto_nominal_id
                LEFT JOIN expedientes_personal ep ON ep.relacion_laboral_id = rl.id
                WHERE rl.empresa_id = :emp
                  AND rl.circuito_pago = :circ
                  AND rl.estatus IN ('ACTIVO', 'PREALTA')
                  AND (ep.id IS NULL OR ep.estatus IN ('LISTO_MERQRY', 'LISTO_PRENOMINA', 'ACTIVO'))
                ORDER BY rl.numero_empleado
                """
            ),
            {"emp": empresa_id, "circ": circuito_destino},
        )
    ]

    # Doble candado de separacion absoluta de circuitos
    assert all(r["circuito_pago"] == circuito_destino for r in rows)

    exp_row = (
        await db.execute(
            text(
                """
                INSERT INTO merqry_exports_nomina (
                    empresa_id, circuito_destino, periodo_label, total_registros,
                    payload_export, generado_por_usuario_id
                ) VALUES (
                    :emp, :circ, :per, :tot, CAST(:pay AS jsonb), CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, empresa_id, circuito_destino, periodo_label, total_registros, creado_en
                """
            ),
            {
                "emp": empresa_id,
                "circ": circuito_destino,
                "per": periodo_label.strip(),
                "tot": len(rows),
                "pay": json.dumps(rows, default=str),
                "uid": actor.usuario_id,
            },
        )
    ).first()

    await registrar_auditoria(
        db,
        actor,
        modulo="merqry_sync",
        accion=f"EXPORT_{circuito_destino}",
        tipo_entidad="MERQRY_EXPORT",
        id_entidad=exp_row.id,
        empresa_id=empresa_id,
        datos_despues={"circuito_destino": circuito_destino, "total_registros": len(rows)},
    )
    await db.commit()
    return {**dict(exp_row._mapping), "registros": rows}


@router.post("/exports/imss", status_code=status.HTTP_201_CREATED)
async def exportar_circuito_imss_merqry(
    data: GenerarExportIn,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """Genera paquete controlado EXCLUSIVAMENTE para circuito IMSS -> Merqry."""
    return await _generar_export_circuito(
        db,
        actor,
        empresa_id=data.empresa_id,
        periodo_label=data.periodo_label,
        circuito_destino="IMSS_MERQRY",
    )


@router.post("/exports/especial-contabilidad", status_code=status.HTTP_201_CREATED)
async def exportar_circuito_especial_contabilidad(
    data: GenerarExportIn,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """Genera paquete controlado EXCLUSIVAMENTE para circuito Especial (efectivo) -> Contabilidad."""
    return await _generar_export_circuito(
        db,
        actor,
        empresa_id=data.empresa_id,
        periodo_label=data.periodo_label,
        circuito_destino="ESPECIAL_CONTABILIDAD",
    )
