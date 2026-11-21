from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    AuthenticatedActor,
    filter_rows_by_scope,
    require_permission,
)

router = APIRouter(prefix="/api/v1/campo", tags=["Operación de Campo"])

ELIGIBILITY_SNAPSHOT_TTL_HOURS = 12


@router.get("/eligibility/daily")
async def obtener_elegibilidad_diaria(
    fecha: Optional[date] = Query(default=None),
    empresa_id: Optional[int] = Query(default=None),
    unidad_operativa_id: Optional[int] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("campo.elegibilidad.leer")),
    db: AsyncSession = Depends(get_db),
):
    """
    Contrato minimo RH -> Campo: DailyEligibleWorker.v0.1
    - Devuelve exclusivamente identidad operativa minima, ambito, elegibilidad y operaciones autorizadas.
    - EXCLUYE estrictamente salarios, CURP, RFC, NSS, CLABE, banco, telefono, email, circuito_pago
      y cualquier dato de expediente/disciplinario.
    - Incluye TTL explicito (expires_at): un snapshot offline vencido no concede autorizacion indefinida.
    """
    target_date = fecha or date.today()
    clauses = ["p.activo = TRUE"]
    params: Dict[str, Any] = {"f": target_date}

    if empresa_id is not None:
        clauses.append("rl.empresa_id = :emp")
        params["emp"] = empresa_id
    if unidad_operativa_id is not None:
        clauses.append("rl.unidad_operativa_id = :uo")
        params["uo"] = unidad_operativa_id

    where = "WHERE " + " AND ".join(clauses)

    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT
                    p.id::text AS person_id,
                    rl.id::text AS relacion_laboral_id,
                    rl.numero_empleado,
                    p.nombre || ' ' || p.apellido_paterno AS nombre_operativo,
                    p.clave_interna_qr,
                    rl.empresa_id,
                    rl.sucursal_id,
                    rl.unidad_operativa_id,
                    rl.estatus AS estatus_relacion,
                    pu.codigo_puesto AS puesto_nominal_codigo,
                    COALESCE(
                        (
                            SELECT fot.funcion_operativa
                            FROM funciones_operativas_temporales fot
                            WHERE fot.relacion_laboral_id = rl.id
                              AND fot.activa = TRUE
                              AND fot.fecha_inicio <= :f
                              AND (fot.fecha_fin IS NULL OR fot.fecha_fin >= :f)
                            ORDER BY fot.creado_en DESC
                            LIMIT 1
                        ),
                        pu.codigo_puesto
                    ) AS funcion_operativa_vigente,
                    COALESCE(e.induccion_inocuidad_completada, TRUE) AS induccion_bpa_vigente
                FROM relaciones_laborales rl
                JOIN personas p ON p.id = rl.persona_id
                JOIN puestos pu ON pu.id = rl.puesto_nominal_id
                LEFT JOIN empleados e ON e.id = rl.empleado_legacy_id
                {where}
                ORDER BY rl.numero_empleado
                """
            ),
            params,
        )
    ]

    scoped = filter_rows_by_scope(rows, actor, "campo.elegibilidad.leer")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=ELIGIBILITY_SNAPSHOT_TTL_HOURS)

    workers: List[Dict[str, Any]] = []
    for r in scoped:
        elegible = r["estatus_relacion"] == "ACTIVO"
        ops: List[str] = []
        if elegible:
            ops.extend(["TRASPLANTE", "LABORES_CULTURALES"])
            if r["induccion_bpa_vigente"]:
                ops.append("COSECHA")
        workers.append(
            {
                "person_id": r["person_id"],
                "relacion_laboral_id": r["relacion_laboral_id"],
                "numero_empleado": r["numero_empleado"],
                "nombre_operativo": r["nombre_operativo"],
                "clave_interna_qr": r["clave_interna_qr"],
                "empresa_id": r["empresa_id"],
                "sucursal_id": r["sucursal_id"],
                "unidad_operativa_id": r["unidad_operativa_id"],
                "funcion_operativa_vigente": r["funcion_operativa_vigente"],
                "elegible_hoy": elegible,
                "operaciones_autorizadas": ops,
            }
        )

    return {
        "contract_version": "DailyEligibleWorker.v0.1",
        "fecha": target_date.isoformat(),
        "generated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ELIGIBILITY_SNAPSHOT_TTL_HOURS * 3600,
        "workers": workers,
    }
