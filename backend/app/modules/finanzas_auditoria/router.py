"""Router de Fase 4: Presupuestos, Gastos por Circuito, Conciliacion Multi-Etapa, Auditoria y Reporte Ejecutivo."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.config import settings
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission
from app.modules.finanzas_auditoria.service import (
    calcular_conciliacion_operativa,
    compute_conciliacion_hash,
)

router = APIRouter(
    prefix="/api/v1/finanzas",
    tags=["Finanzas, Conciliación y Auditoría Avanzada (Fase 4)"],
)

RUBROS_PATTERN = "^(MANO_OBRA_IMSS|MANO_OBRA_ESPECIAL|INSUMOS_FITO|TRASPLANTE|EMPAQUE|LOGISTICA)$"


class PresupuestoIn(BaseModel):
    empresa_id: int
    unidad_operativa_id: Optional[int] = None
    anio: int = Field(..., ge=2024, le=2100)
    periodo_clave: str = Field(..., min_length=4, max_length=20)
    rubro: str = Field(..., pattern=RUBROS_PATTERN)
    monto_presupuestado: float = Field(..., ge=0)
    notas: Optional[str] = None


class GastoOperativoIn(BaseModel):
    empresa_id: int
    sucursal_id: Optional[int] = None
    unidad_operativa_id: Optional[int] = None
    lote_id: Optional[int] = None
    fecha: date
    periodo_clave: str = Field(..., min_length=4, max_length=20)
    rubro: str = Field(..., pattern=RUBROS_PATTERN)
    circuito_origen: str = Field(..., pattern="^(IMSS_MERQRY|ESPECIAL_CONTABILIDAD|OPERACION_GENERAL)$")
    concepto: str = Field(..., min_length=3, max_length=160)
    monto: float = Field(..., gt=0)
    folio_comprobante: Optional[str] = Field(None, max_length=80)


class ConciliacionIn(BaseModel):
    empresa_id: int
    fecha_inicio: date
    fecha_fin: date


class TransicionConciliacionIn(BaseModel):
    nuevo_estatus: str = Field(..., pattern="^(CONCILIADA|CERRADA_AUDITORIA)$")


def _parse_uuid_or_404(raw: str, label: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} invalido o no encontrado.") from exc


@router.post("/presupuestos", status_code=status.HTTP_201_CREATED)
async def upsert_presupuesto_operativo(
    data: PresupuestoIn,
    actor: AuthenticatedActor = Depends(require_permission("finanzas.presupuesto.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "finanzas.presupuesto.gestionar",
        empresa_id=data.empresa_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=3,
    )

    existing = (
        await db.execute(
            text(
                """
                SELECT id::text AS id
                FROM fin_presupuestos_operativos
                WHERE empresa_id = :emp
                  AND COALESCE(unidad_operativa_id, 0) = COALESCE(:uo, 0)
                  AND anio = :anio
                  AND periodo_clave = :per
                  AND rubro = :rubro
                """
            ),
            {
                "emp": data.empresa_id,
                "uo": data.unidad_operativa_id,
                "anio": data.anio,
                "per": data.periodo_clave.strip(),
                "rubro": data.rubro,
            },
        )
    ).mappings().first()

    if existing:
        row = (
            await db.execute(
                text(
                    """
                    UPDATE fin_presupuestos_operativos
                       SET monto_presupuestado = :monto,
                           notas = :notas,
                           actualizado_en = NOW()
                     WHERE id = CAST(:pid AS UUID)
                    RETURNING id::text, empresa_id, unidad_operativa_id, anio, periodo_clave,
                              rubro, monto_presupuestado::float AS monto_presupuestado, notas
                    """
                ),
                {"pid": existing["id"], "monto": data.monto_presupuestado, "notas": data.notas},
            )
        ).mappings().first()
    else:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO fin_presupuestos_operativos (
                        empresa_id, unidad_operativa_id, anio, periodo_clave,
                        rubro, monto_presupuestado, notas, creado_por_usuario_id
                    ) VALUES (
                        :emp, :uo, :anio, :per, :rubro, :monto, :notas, CAST(:uid AS UUID)
                    )
                    RETURNING id::text, empresa_id, unidad_operativa_id, anio, periodo_clave,
                              rubro, monto_presupuestado::float AS monto_presupuestado, notas
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "uo": data.unidad_operativa_id,
                    "anio": data.anio,
                    "per": data.periodo_clave.strip(),
                    "rubro": data.rubro,
                    "monto": data.monto_presupuestado,
                    "notas": data.notas,
                    "uid": actor.usuario_id,
                },
            )
        ).mappings().first()

    out = dict(row)
    await registrar_auditoria(
        db,
        actor,
        modulo="finanzas_auditoria",
        accion="UPSERT_PRESUPUESTO",
        tipo_entidad="fin_presupuestos_operativos",
        id_entidad=out["id"],
        empresa_id=data.empresa_id,
        unidad_operativa_id=data.unidad_operativa_id,
        datos_despues=out,
    )
    await db.commit()
    return out


@router.post("/gastos", status_code=status.HTTP_201_CREATED)
async def registrar_gasto_operativo(
    data: GastoOperativoIn,
    actor: AuthenticatedActor = Depends(require_permission("finanzas.presupuesto.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "finanzas.presupuesto.gestionar",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=3,
    )

    # Candado de circuito financiero
    if data.rubro == "MANO_OBRA_IMSS" and data.circuito_origen != "IMSS_MERQRY":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CIRCUIT_MISMATCH",
                "message": "MANO_OBRA_IMSS solo puede registrarse bajo circuito_origen='IMSS_MERQRY'.",
            },
        )
    if data.rubro == "MANO_OBRA_ESPECIAL" and data.circuito_origen != "ESPECIAL_CONTABILIDAD":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CIRCUIT_MISMATCH",
                "message": "MANO_OBRA_ESPECIAL solo puede registrarse bajo circuito_origen='ESPECIAL_CONTABILIDAD'.",
            },
        )

    row = (
        await db.execute(
            text(
                """
                INSERT INTO fin_gastos_operativos (
                    empresa_id, sucursal_id, unidad_operativa_id, lote_id,
                    fecha, periodo_clave, rubro, circuito_origen,
                    concepto, monto, folio_comprobante, creado_por_usuario_id
                ) VALUES (
                    :emp, :suc, :uo, :lote,
                    :fecha, :per, :rubro, :circ,
                    :conc, :monto, :folio, CAST(:uid AS UUID)
                )
                RETURNING id::text, empresa_id, unidad_operativa_id, fecha::text,
                          periodo_clave, rubro, circuito_origen, concepto,
                          monto::float AS monto, folio_comprobante
                """
            ),
            {
                "emp": data.empresa_id,
                "suc": data.sucursal_id,
                "uo": data.unidad_operativa_id,
                "lote": data.lote_id,
                "fecha": data.fecha,
                "per": data.periodo_clave.strip(),
                "rubro": data.rubro,
                "circ": data.circuito_origen,
                "conc": data.concepto.strip(),
                "monto": data.monto,
                "folio": data.folio_comprobante,
                "uid": actor.usuario_id,
            },
        )
    ).mappings().first()
    out = dict(row)

    # Evaluar semáforo presupuestal en el periodo/rubro
    pres = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(monto_presupuestado), 0) AS presupuestado
                FROM fin_presupuestos_operativos
                WHERE empresa_id = :emp AND periodo_clave = :per AND rubro = :rubro
                """
            ),
            {"emp": data.empresa_id, "per": data.periodo_clave.strip(), "rubro": data.rubro},
        )
    ).scalar()
    ejercido = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(monto), 0) AS ejercido
                FROM fin_gastos_operativos
                WHERE empresa_id = :emp AND periodo_clave = :per AND rubro = :rubro
                """
            ),
            {"emp": data.empresa_id, "per": data.periodo_clave.strip(), "rubro": data.rubro},
        )
    ).scalar()

    pres_d = Decimal(str(pres or 0))
    ej_d = Decimal(str(ejercido or 0))
    pct = float((ej_d / pres_d * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if pres_d > 0 else 0.0
    semaforo = "SIN_PRESUPUESTO" if pres_d == 0 else ("SOBREGIRO" if pct > 100 else ("ALERTA" if pct >= 85 else "OK"))

    await registrar_auditoria(
        db,
        actor,
        modulo="finanzas_auditoria",
        accion="REGISTRAR_GASTO",
        tipo_entidad="fin_gastos_operativos",
        id_entidad=out["id"],
        empresa_id=data.empresa_id,
        unidad_operativa_id=data.unidad_operativa_id,
        datos_despues={**out, "semaforo_presupuesto": semaforo, "porcentaje_ejercido": pct},
    )
    await db.commit()
    return {
        "gasto": out,
        "control_presupuestal": {
            "presupuestado": float(pres_d),
            "ejercido_acumulado": float(ej_d),
            "porcentaje_ejercido": pct,
            "semaforo": semaforo,
        },
    }


@router.get("/presupuestos/control")
async def control_presupuestal(
    empresa_id: int = Query(...),
    periodo_clave: str = Query(...),
    actor: AuthenticatedActor = Depends(require_permission("finanzas.reportes.leer", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(actor, "finanzas.reportes.leer", empresa_id=empresa_id, min_level=2)

    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                WITH p AS (
                    SELECT rubro, COALESCE(SUM(monto_presupuestado), 0) AS presupuestado
                    FROM fin_presupuestos_operativos
                    WHERE empresa_id = :emp AND periodo_clave = :per
                    GROUP BY rubro
                ),
                g AS (
                    SELECT rubro, COALESCE(SUM(monto), 0) AS ejercido
                    FROM fin_gastos_operativos
                    WHERE empresa_id = :emp AND periodo_clave = :per
                    GROUP BY rubro
                )
                SELECT
                    COALESCE(p.rubro, g.rubro) AS rubro,
                    COALESCE(p.presupuestado, 0)::float AS presupuestado,
                    COALESCE(g.ejercido, 0)::float AS ejercido
                FROM p
                FULL OUTER JOIN g ON g.rubro = p.rubro
                ORDER BY rubro
                """
            ),
            {"emp": empresa_id, "per": periodo_clave.strip()},
        )
    ]

    enriched = []
    for r in rows:
        pres = Decimal(str(r["presupuestado"]))
        ej = Decimal(str(r["ejercido"]))
        var = pres - ej
        pct = float((ej / pres * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if pres > 0 else 0.0
        sem = "SIN_PRESUPUESTO" if pres == 0 else ("SOBREGIRO" if pct > 100 else ("ALERTA" if pct >= 85 else "OK"))
        enriched.append(
            {
                **r,
                "disponible": float(var),
                "porcentaje_ejercido": pct,
                "semaforo": sem,
            }
        )

    return {
        "empresa_id": empresa_id,
        "periodo_clave": periodo_clave,
        "rubros": enriched,
        "alertas_sobregiro": [x["rubro"] for x in enriched if x["semaforo"] == "SOBREGIRO"],
    }


@router.post("/conciliaciones", status_code=status.HTTP_201_CREATED)
async def generar_conciliacion_operativa(
    data: ConciliacionIn,
    actor: AuthenticatedActor = Depends(require_permission("finanzas.conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(actor, "finanzas.conciliar", empresa_id=data.empresa_id, min_level=3)
    if data.fecha_fin < data.fecha_inicio:
        raise HTTPException(status_code=400, detail="fecha_fin debe ser >= fecha_inicio.")

    calc = await calcular_conciliacion_operativa(
        db,
        empresa_id=data.empresa_id,
        fecha_inicio=data.fecha_inicio,
        fecha_fin=data.fecha_fin,
    )
    nums = calc["numerics"]

    row = (
        await db.execute(
            text(
                """
                INSERT INTO fin_conciliaciones_operativas (
                    empresa_id, fecha_inicio, fecha_fin, estatus,
                    cajas_campo_exportacion, cajas_campo_nacional, cajas_campo_merma,
                    cajas_trasladadas_empaque, delta_cajas_campo_vs_empaque,
                    total_mo_imss_merqry, total_mo_especial_contabilidad,
                    total_insumos_fito, total_otros_gastos, costo_total_directo,
                    costo_mo_por_caja_exportable, detalle_json,
                    hash_conciliacion_sha256, creado_por_usuario_id
                ) VALUES (
                    :emp, :fi, :ff, 'BORRADOR',
                    :cexp, :cnac, :cmer,
                    :ctras, :delta,
                    :mo_imss, :mo_esp,
                    :fito, :otros, :ctot,
                    :cmoc, CAST(:det AS JSONB),
                    :hash, CAST(:uid AS UUID)
                )
                RETURNING
                    id::text, empresa_id, fecha_inicio::text, fecha_fin::text, estatus,
                    cajas_campo_exportacion::float, cajas_campo_nacional::float,
                    cajas_campo_merma::float, cajas_trasladadas_empaque::float,
                    delta_cajas_campo_vs_empaque::float,
                    total_mo_imss_merqry::float, total_mo_especial_contabilidad::float,
                    total_insumos_fito::float, total_otros_gastos::float,
                    costo_total_directo::float, costo_mo_por_caja_exportable::float,
                    detalle_json, hash_conciliacion_sha256, creado_en::text
                """
            ),
            {
                "emp": data.empresa_id,
                "fi": data.fecha_inicio,
                "ff": data.fecha_fin,
                "cexp": nums["cajas_exp"],
                "cnac": nums["cajas_nac"],
                "cmer": nums["cajas_merma"],
                "ctras": nums["cajas_trasladadas"],
                "delta": nums["delta_cajas"],
                "mo_imss": nums["total_mo_imss"],
                "mo_esp": nums["total_mo_esp"],
                "fito": nums["total_fito"],
                "otros": nums["total_otros"],
                "ctot": nums["costo_total"],
                "cmoc": nums["costo_mo_caja"],
                "det": json.dumps(calc["detalle"], ensure_ascii=False),
                "hash": calc["hash_conciliacion_sha256"],
                "uid": actor.usuario_id,
            },
        )
    ).mappings().first()
    out = dict(row)

    await registrar_auditoria(
        db,
        actor,
        modulo="finanzas_auditoria",
        accion="GENERAR_CONCILIACION",
        tipo_entidad="fin_conciliaciones_operativas",
        id_entidad=out["id"],
        empresa_id=data.empresa_id,
        datos_despues={"hash_conciliacion_sha256": out["hash_conciliacion_sha256"], "estatus": "BORRADOR"},
    )
    await db.commit()
    return out


@router.patch("/conciliaciones/{conciliacion_id}/transicion")
async def transicionar_conciliacion(
    conciliacion_id: str,
    data: TransicionConciliacionIn,
    actor: AuthenticatedActor = Depends(require_permission("finanzas.conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    cid = _parse_uuid_or_404(conciliacion_id, "conciliacion_id")
    curr = (
        await db.execute(
            text(
                """
                SELECT id::text, empresa_id, estatus, hash_conciliacion_sha256
                FROM fin_conciliaciones_operativas
                WHERE id = CAST(:cid AS UUID)
                FOR UPDATE
                """
            ),
            {"cid": cid},
        )
    ).mappings().first()
    if not curr:
        raise HTTPException(status_code=404, detail="Conciliación operativa no encontrada.")

    assert_scope(actor, "finanzas.conciliar", empresa_id=curr["empresa_id"], min_level=3)

    if curr["estatus"] == "CERRADA_AUDITORIA":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONCILIACION_INMUTABLE",
                "message": "La conciliación ya se encuentra en CERRADA_AUDITORIA y es inmutable.",
                "hash_conciliacion_sha256": curr["hash_conciliacion_sha256"],
            },
        )

    allowed_transitions = {
        "BORRADOR": {"CONCILIADA"},
        "CONCILIADA": {"CERRADA_AUDITORIA"},
    }
    if data.nuevo_estatus not in allowed_transitions.get(curr["estatus"], set()):
        raise HTTPException(
            status_code=400,
            detail=f"Transición inválida: {curr['estatus']} -> {data.nuevo_estatus}.",
        )

    updated = (
        await db.execute(
            text(
                """
                UPDATE fin_conciliaciones_operativas
                   SET estatus = CAST(:est AS VARCHAR),
                       cerrado_por_usuario_id = CASE WHEN CAST(:est AS VARCHAR) = 'CERRADA_AUDITORIA' THEN CAST(:uid AS UUID) ELSE cerrado_por_usuario_id END,
                       cerrado_en = CASE WHEN CAST(:est AS VARCHAR) = 'CERRADA_AUDITORIA' THEN NOW() ELSE cerrado_en END
                 WHERE id = CAST(:cid AS UUID)
                RETURNING id::text, empresa_id, estatus, hash_conciliacion_sha256, cerrado_en::text
                """
            ),
            {"cid": cid, "est": data.nuevo_estatus, "uid": actor.usuario_id},
        )
    ).mappings().first()
    out = dict(updated)

    await registrar_auditoria(
        db,
        actor,
        modulo="finanzas_auditoria",
        accion=f"CONCILIACION_{data.nuevo_estatus}",
        tipo_entidad="fin_conciliaciones_operativas",
        id_entidad=cid,
        empresa_id=curr["empresa_id"],
        datos_antes={"estatus": curr["estatus"]},
        datos_despues=out,
    )
    await db.commit()
    return out


@router.get("/auditoria/eventos")
async def consultar_auditoria_avanzada(
    empresa_id: Optional[int] = Query(None),
    modulo: Optional[str] = Query(None),
    accion: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    actor: AuthenticatedActor = Depends(require_permission("auditoria.leer", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    if empresa_id is not None:
        assert_scope(actor, "auditoria.leer", empresa_id=empresa_id, min_level=3)

    clauses = ["1=1"]
    params: Dict[str, Any] = {"lim": limit}
    if empresa_id is not None:
        clauses.append("empresa_id = :emp")
        params["emp"] = empresa_id
    if modulo:
        clauses.append("modulo = :mod")
        params["mod"] = modulo.strip()
    if accion:
        clauses.append("accion = :acc")
        params["acc"] = accion.strip()

    eventos = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT
                    id, actor_username, rol_codigo, empresa_id, unidad_operativa_id,
                    modulo, accion, tipo_entidad, id_entidad, datos_despues, creado_en::text
                FROM auditoria_universal
                WHERE {' AND '.join(clauses)}
                ORDER BY id DESC
                LIMIT :lim
                """
            ),
            params,
        )
    ]

    bloqueos_merqry = (
        await db.execute(
            text("SELECT COUNT(*) FROM merqry_write_audit_log WHERE severidad = 'BLOCKED'")
        )
    ).scalar()
    excepciones_vencidas = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM update_ready_excepciones
                WHERE estatus = 'ACTIVA' AND fecha_limite < CURRENT_DATE
                """
            )
        )
    ).scalar()

    return {
        "total_eventos": len(eventos),
        "eventos": eventos,
        "resumen_seguridad": {
            "bloqueos_firewall_merqry": int(bloqueos_merqry or 0),
            "excepciones_update_ready_vencidas": int(excepciones_vencidas or 0),
            "merqry_write_enabled": settings.merqry_write_enabled,
        },
    }


@router.get("/auditoria/integridad")
async def verificar_integridad_criptografica(
    empresa_id: int = Query(...),
    actor: AuthenticatedActor = Depends(require_permission("auditoria.leer", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """Recalcula los SHA-256 de conciliaciones cerradas para detectar cualquier manipulacion fuera de flujo."""
    assert_scope(actor, "auditoria.leer", empresa_id=empresa_id, min_level=3)

    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT
                    id::text, empresa_id, fecha_inicio, fecha_fin, estatus,
                    cajas_campo_exportacion, cajas_campo_nacional, cajas_campo_merma,
                    cajas_trasladadas_empaque, delta_cajas_campo_vs_empaque,
                    total_mo_imss_merqry, total_mo_especial_contabilidad,
                    total_insumos_fito, total_otros_gastos, costo_total_directo,
                    costo_mo_por_caja_exportable, hash_conciliacion_sha256
                FROM fin_conciliaciones_operativas
                WHERE empresa_id = :emp
                ORDER BY creado_en DESC
                LIMIT 50
                """
            ),
            {"emp": empresa_id},
        )
    ]

    verificaciones: List[Dict[str, Any]] = []
    tampered = 0
    for r in rows:
        core = {
            "empresa_id": r["empresa_id"],
            "fecha_inicio": r["fecha_inicio"].isoformat(),
            "fecha_fin": r["fecha_fin"].isoformat(),
            "cajas_campo_exportacion": str(Decimal(str(r["cajas_campo_exportacion"])).quantize(Decimal("0.01"))),
            "cajas_campo_nacional": str(Decimal(str(r["cajas_campo_nacional"])).quantize(Decimal("0.01"))),
            "cajas_campo_merma": str(Decimal(str(r["cajas_campo_merma"])).quantize(Decimal("0.01"))),
            "cajas_trasladadas_empaque": str(Decimal(str(r["cajas_trasladadas_empaque"])).quantize(Decimal("0.01"))),
            "delta_cajas_campo_vs_empaque": str(Decimal(str(r["delta_cajas_campo_vs_empaque"])).quantize(Decimal("0.01"))),
            "total_mo_imss_merqry": str(Decimal(str(r["total_mo_imss_merqry"])).quantize(Decimal("0.01"))),
            "total_mo_especial_contabilidad": str(Decimal(str(r["total_mo_especial_contabilidad"])).quantize(Decimal("0.01"))),
            "total_insumos_fito": str(Decimal(str(r["total_insumos_fito"])).quantize(Decimal("0.01"))),
            "total_otros_gastos": str(Decimal(str(r["total_otros_gastos"])).quantize(Decimal("0.01"))),
            "costo_total_directo": str(Decimal(str(r["costo_total_directo"])).quantize(Decimal("0.01"))),
            "costo_mo_por_caja_exportable": str(Decimal(str(r["costo_mo_por_caja_exportable"])).quantize(Decimal("0.0001"))),
        }
        expected = compute_conciliacion_hash(core)
        ok = expected == r["hash_conciliacion_sha256"]
        if not ok:
            tampered += 1
        verificaciones.append(
            {
                "conciliacion_id": r["id"],
                "estatus": r["estatus"],
                "integridad": "INTEGRIDAD_OK" if ok else "TAMPER_DETECTED",
                "hash_almacenado": r["hash_conciliacion_sha256"],
                "hash_recalculado": expected,
            }
        )

    return {
        "empresa_id": empresa_id,
        "estado_global": "INTEGRIDAD_OK" if tampered == 0 else "TAMPER_DETECTED",
        "conciliaciones_verificadas": len(verificaciones),
        "alteraciones_detectadas": tampered,
        "detalle": verificaciones,
    }


@router.get("/reportes/ejecutivo")
async def reporte_ejecutivo_direccion(
    empresa_id: int = Query(...),
    fecha_inicio: date = Query(...),
    fecha_fin: date = Query(...),
    periodo_clave: Optional[str] = Query(None),
    actor: AuthenticatedActor = Depends(require_permission("finanzas.reportes.leer", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(actor, "finanzas.reportes.leer", empresa_id=empresa_id, min_level=2)
    if fecha_fin < fecha_inicio:
        raise HTTPException(status_code=400, detail="fecha_fin debe ser >= fecha_inicio.")

    emp = (
        await db.execute(
            text("SELECT id, clave, razon_social, nombre_comercial FROM empresas WHERE id = :emp"),
            {"emp": empresa_id},
        )
    ).mappings().first()
    if not emp:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")

    calc = await calcular_conciliacion_operativa(
        db,
        empresa_id=empresa_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    nums = calc["numerics"]
    total_cajas_campo = nums["cajas_exp"] + nums["cajas_nac"] + nums["cajas_merma"]
    pct_merma = (
        float((nums["cajas_merma"] / total_cajas_campo * Decimal("100")).quantize(Decimal("0.01")))
        if total_cajas_campo > 0
        else 0.0
    )

    lotes_phi = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM lotes_produccion
                WHERE empresa_clave = :clave
                  AND estatus_fitosanitario <> 'LIBRE_CORTE'
                  AND activo = TRUE
                """
            ),
            {"clave": emp["clave"]},
        )
    ).scalar()

    presupuesto_resumen = None
    if periodo_clave:
        presupuesto_resumen = await control_presupuestal(
            empresa_id=empresa_id,
            periodo_clave=periodo_clave,
            actor=actor,
            db=db,
        )

    return {
        "empresa": dict(emp),
        "rango": {"fecha_inicio": fecha_inicio.isoformat(), "fecha_fin": fecha_fin.isoformat()},
        "kpis_operativos": {
            "cajas_exportacion": float(nums["cajas_exp"]),
            "cajas_nacional": float(nums["cajas_nac"]),
            "cajas_merma": float(nums["cajas_merma"]),
            "porcentaje_merma_global": pct_merma,
            "cajas_trasladadas_empaque": float(nums["cajas_trasladadas"]),
            "delta_cajas_campo_vs_empaque": float(nums["delta_cajas"]),
            "lotes_bloqueados_phi": int(lotes_phi or 0),
        },
        "kpis_financieros_separados": {
            "mano_obra_imss_merqry": float(nums["total_mo_imss"]),
            "mano_obra_especial_contabilidad": float(nums["total_mo_esp"]),
            "insumos_fitosanitarios": float(nums["total_fito"]),
            "otros_gastos_operativos": float(nums["total_otros"]),
            "costo_total_directo": float(nums["costo_total"]),
            "costo_mo_por_caja_exportable": float(nums["costo_mo_caja"]),
        },
        "control_presupuestal": presupuesto_resumen,
        "seguridad_merqry": {
            "readonly_mirror": settings.merqry_readonly_mode,
            "merqry_write_enabled": settings.merqry_write_enabled,
        },
        "hash_snapshot_sha256": calc["hash_conciliacion_sha256"],
    }
