from datetime import date
from decimal import Decimal
import hashlib
import json
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission
from app.modules.prenomina.motor_semanal import calcular_prenomina_trabajador_semanal

router = APIRouter(prefix="/api/v1/prenomina", tags=["Prenómina Semanal (Fase 3B)"])


class GenerarPrenominaSemanalIn(BaseModel):
    empresa_id: int
    anio: int = Field(..., ge=2024, le=2100)
    semana_seah: int = Field(..., ge=1, le=53)
    fecha_inicio: date
    fecha_fin: date
    regla_id: Optional[int] = None


class TransicionPrenominaIn(BaseModel):
    nuevo_estatus: str = Field(..., pattern="^(AUTORIZADA|PAGABLE|EXPORTADA|RECIBIDA)$")


def _uuid(raw: str, label: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} inválido o no encontrado.") from exc


@router.post("/semanal/generar", status_code=status.HTTP_201_CREATED)
async def generar_prenomina_semanal(
    data: GenerarPrenominaSemanalIn,
    actor: AuthenticatedActor = Depends(require_permission("prenomina.calcular", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """
    Calcula la prenomina semanal sobre capturas AUTORIZADAS por oficina (nunca capturas sin revisar).
    Si la semana ya esta en PAGABLE/EXPORTADA/RECIBIDA -> 409 PRENOMINA_INMUTABLE.
    Separa estrictamente totales IMSS_MERQRY vs ESPECIAL_CONTABILIDAD.
    """
    assert_scope(actor, "prenomina.calcular", empresa_id=data.empresa_id, min_level=3)
    if data.fecha_fin < data.fecha_inicio:
        raise HTTPException(status_code=400, detail="fecha_fin debe ser >= fecha_inicio.")

    # Verificar si ya existe prenomina para esa empresa/anio/semana
    prev = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, estatus, hash_cierre_inmutable
                FROM prenomina_semanal
                WHERE empresa_id = :emp AND anio = :anio AND semana_seah = :sem
                FOR UPDATE
                """
            ),
            {"emp": data.empresa_id, "anio": data.anio, "sem": data.semana_seah},
        )
    ).first()
    if prev and prev.estatus in ("PAGABLE", "EXPORTADA", "RECIBIDA"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PRENOMINA_INMUTABLE",
                "message": f"La prenómina semana {data.semana_seah}/{data.anio} ya tiene cierre inmutable ({prev.estatus}).",
                "hash_cierre_inmutable": prev.hash_cierre_inmutable,
            },
        )

    # Cargar regla configurable vigente
    if data.regla_id:
        regla = (
            await db.execute(
                text("SELECT * FROM prenomina_reglas_semanales WHERE id = :rid AND empresa_id = :emp"),
                {"rid": data.regla_id, "emp": data.empresa_id},
            )
        ).first()
    else:
        regla = (
            await db.execute(
                text(
                    "SELECT * FROM prenomina_reglas_semanales WHERE empresa_id = :emp AND activa = TRUE ORDER BY id LIMIT 1"
                ),
                {"emp": data.empresa_id},
            )
        ).first()
    if not regla:
        raise HTTPException(status_code=404, detail="No existe regla semanal activa para esta empresa.")

    # Agregar SOLO capturas en estado AUTORIZADA (excluye CAPTURADA y CIERRE_TECNICO sin revision!)
    agg = (
        await db.execute(
            text(
                """
                SELECT
                    c.persona_id::text AS persona_id,
                    c.relacion_laboral_id::text AS relacion_laboral_id,
                    rl.numero_empleado,
                    c.circuito_pago,
                    COUNT(DISTINCT c.fecha) AS dias_trabajados,
                    COALESCE(SUM(CASE WHEN NOT c.es_domingo THEN (c.cajas_exportacion + c.cajas_nacional) ELSE 0 END), 0) AS cajas_ls,
                    COALESCE(SUM(CASE WHEN c.es_domingo THEN (c.cajas_exportacion + c.cajas_nacional) ELSE 0 END), 0) AS cajas_domingo,
                    COALESCE(SUM(c.cajas_merma_rezaga), 0) AS cajas_merma
                FROM campo_capturas_cosecha c
                JOIN relaciones_laborales rl ON rl.id = c.relacion_laboral_id
                WHERE c.empresa_id = :emp
                  AND c.fecha BETWEEN :fi AND :ff
                  AND c.estatus_flujo = 'AUTORIZADA'
                GROUP BY c.persona_id, c.relacion_laboral_id, rl.numero_empleado, c.circuito_pago
                ORDER BY rl.numero_empleado
                """
            ),
            {"emp": data.empresa_id, "fi": data.fecha_inicio, "ff": data.fecha_fin},
        )
    ).all()

    if not agg:
        raise HTTPException(
            status_code=409,
            detail="SIN_CAPTURAS_AUTORIZADAS: No hay capturas en estado AUTORIZADA para el rango semanal.",
        )

    if prev:
        pre_id = prev.id
        await db.execute(
            text("DELETE FROM prenomina_semanal_detalle WHERE prenomina_semanal_id = CAST(:pid AS uuid)"),
            {"pid": pre_id},
        )
    else:
        pre_id = (
            await db.execute(
                text(
                    """
                    INSERT INTO prenomina_semanal (
                        empresa_id, anio, semana_seah, fecha_inicio, fecha_fin,
                        regla_id, estatus, generado_por_usuario_id
                    ) VALUES (
                        :emp, :anio, :sem, :fi, :ff, :rid, 'EN_REVISION', CAST(:uid AS uuid)
                    )
                    RETURNING id::text
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "anio": data.anio,
                    "sem": data.semana_seah,
                    "fi": data.fecha_inicio,
                    "ff": data.fecha_fin,
                    "rid": regla.id,
                    "uid": actor.usuario_id,
                },
            )
        ).scalar()

    tot_imss = Decimal("0.00")
    tot_esp = Decimal("0.00")
    detalles = []

    for r in agg:
        calc = calcular_prenomina_trabajador_semanal(
            cajas_ls=Decimal(str(r.cajas_ls)),
            cajas_domingo=Decimal(str(r.cajas_domingo)),
            cajas_merma=Decimal(str(r.cajas_merma)),
            dias_trabajados=int(r.dias_trabajados),
            tarifa_caja_ls=Decimal(str(regla.tarifa_caja_ls)),
            domingo_umbral_cajas=Decimal(str(regla.domingo_umbral_cajas)),
            domingo_tarifa_base=Decimal(str(regla.domingo_tarifa_base)),
            domingo_tarifa_excedente=Decimal(str(regla.domingo_tarifa_excedente)),
            minimo_semanal_garantizado=Decimal(str(regla.minimo_semanal_garantizado)),
            dias_minimos_para_garantia=int(regla.dias_minimos_para_garantia),
            alerta_merma_pct=Decimal(str(regla.alerta_merma_pct)),
        )
        if r.circuito_pago == "IMSS_MERQRY":
            tot_imss += calc["total_pagar"]
        else:
            tot_esp += calc["total_pagar"]

        await db.execute(
            text(
                """
                INSERT INTO prenomina_semanal_detalle (
                    prenomina_semanal_id, persona_id, relacion_laboral_id, numero_empleado,
                    circuito_pago, dias_trabajados, cajas_ls, cajas_domingo, cajas_merma,
                    porcentaje_merma_semanal, alerta_merma, pago_ls, pago_domingo_base,
                    pago_domingo_excedente, subtotal_destajo, ajuste_minimo_semanal, total_pagar
                ) VALUES (
                    CAST(:pre AS uuid), CAST(:pid AS uuid), CAST(:rlid AS uuid), :num,
                    :circ, :dias, :cls, :cdom, :cmer,
                    :pmer, :al, :pls, :pdb,
                    :pde, :sub, :aju, :tot
                )
                """
            ),
            {
                "pre": pre_id,
                "pid": r.persona_id,
                "rlid": r.relacion_laboral_id,
                "num": r.numero_empleado,
                "circ": r.circuito_pago,
                "dias": int(r.dias_trabajados),
                "cls": r.cajas_ls,
                "cdom": r.cajas_domingo,
                "cmer": r.cajas_merma,
                "pmer": calc["porcentaje_merma_semanal"],
                "al": calc["alerta_merma"],
                "pls": calc["pago_ls"],
                "pdb": calc["pago_domingo_base"],
                "pde": calc["pago_domingo_excedente"],
                "sub": calc["subtotal_destajo"],
                "aju": calc["ajuste_minimo_semanal"],
                "tot": calc["total_pagar"],
            },
        )
        detalles.append(
            {
                "numero_empleado": r.numero_empleado,
                "circuito_pago": r.circuito_pago,
                "cajas_ls": float(r.cajas_ls),
                "cajas_domingo": float(r.cajas_domingo),
                "pago_ls": float(calc["pago_ls"]),
                "pago_domingo_base": float(calc["pago_domingo_base"]),
                "pago_domingo_excedente": float(calc["pago_domingo_excedente"]),
                "subtotal_destajo": float(calc["subtotal_destajo"]),
                "ajuste_minimo_semanal": float(calc["ajuste_minimo_semanal"]),
                "total_pagar": float(calc["total_pagar"]),
                "alerta_merma": calc["alerta_merma"],
            }
        )

    tot_gen = tot_imss + tot_esp
    await db.execute(
        text(
            """
            UPDATE prenomina_semanal
               SET estatus = 'EN_REVISION',
                   total_trabajadores = :cnt,
                   total_imss_merqry = :imss,
                   total_especial_contabilidad = :esp,
                   total_general = :gen
             WHERE id = CAST(:pre AS uuid)
            """
        ),
        {"cnt": len(detalles), "imss": tot_imss, "esp": tot_esp, "gen": tot_gen, "pre": pre_id},
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="prenomina",
        accion="GENERAR_PRENOMINA_SEMANAL",
        tipo_entidad="PRENOMINA_SEMANAL",
        id_entidad=pre_id,
        empresa_id=data.empresa_id,
        datos_despues={
            "semana_seah": data.semana_seah,
            "total_imss_merqry": str(tot_imss),
            "total_especial_contabilidad": str(tot_esp),
        },
    )
    await db.commit()
    return {
        "prenomina_id": pre_id,
        "estatus": "EN_REVISION",
        "total_trabajadores": len(detalles),
        "total_imss_merqry": float(tot_imss),
        "total_especial_contabilidad": float(tot_esp),
        "total_general": float(tot_gen),
        "detalles": detalles,
    }


@router.patch("/semanal/{prenomina_id}/transicion")
async def transicionar_prenomina_semanal(
    prenomina_id: str,
    data: TransicionPrenominaIn,
    actor: AuthenticatedActor = Depends(require_permission("prenomina.autorizar_cerrar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """
    Maquina estricta: EN_REVISION -> AUTORIZADA -> PAGABLE (cierre inmutable + SHA-256) -> EXPORTADA -> RECIBIDA.
    """
    pid = _uuid(prenomina_id, "Prenómina semanal")
    pre = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, anio, semana_seah, fecha_inicio, fecha_fin,
                       estatus, total_imss_merqry, total_especial_contabilidad, total_general
                FROM prenomina_semanal
                WHERE id = CAST(:id AS uuid)
                FOR UPDATE
                """
            ),
            {"id": pid},
        )
    ).first()
    if not pre:
        raise HTTPException(status_code=404, detail="Prenómina semanal no encontrada.")
    assert_scope(actor, "prenomina.autorizar_cerrar", empresa_id=pre.empresa_id, min_level=3)

    transitions = {
        "BORRADOR": {"EN_REVISION"},
        "EN_REVISION": {"AUTORIZADA"},
        "AUTORIZADA": {"PAGABLE"},
        "PAGABLE": {"EXPORTADA"},
        "EXPORTADA": {"RECIBIDA"},
    }
    if data.nuevo_estatus not in transitions.get(pre.estatus, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Transición inválida en prenómina: {pre.estatus} -> {data.nuevo_estatus}.",
        )

    hash_inm = None
    if data.nuevo_estatus == "AUTORIZADA":
        await db.execute(
            text(
                """
                UPDATE prenomina_semanal
                   SET estatus = 'AUTORIZADA',
                       autorizado_por_usuario_id = CAST(:uid AS uuid),
                       autorizado_en = NOW()
                 WHERE id = CAST(:id AS uuid)
                """
            ),
            {"uid": actor.usuario_id, "id": pid},
        )
    elif data.nuevo_estatus == "PAGABLE":
        det_rows = [
            dict(r._mapping)
            for r in await db.execute(
                text(
                    """
                    SELECT numero_empleado, circuito_pago, total_pagar::text AS total_pagar
                    FROM prenomina_semanal_detalle
                    WHERE prenomina_semanal_id = CAST(:id AS uuid)
                    ORDER BY numero_empleado
                    """
                ),
                {"id": pid},
            )
        ]
        canonical = json.dumps(
            {
                "prenomina_id": pid,
                "empresa_id": pre.empresa_id,
                "anio": pre.anio,
                "semana_seah": pre.semana_seah,
                "detalles": det_rows,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        hash_inm = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        await db.execute(
            text(
                """
                UPDATE prenomina_semanal
                   SET estatus = 'PAGABLE',
                       hash_cierre_inmutable = :h,
                       cerrado_inmutable_en = NOW()
                 WHERE id = CAST(:id AS uuid)
                """
            ),
            {"h": hash_inm, "id": pid},
        )
        await db.execute(
            text(
                """
                UPDATE campo_capturas_cosecha
                   SET estatus_flujo = 'PAGABLE'
                 WHERE empresa_id = :emp
                   AND fecha BETWEEN :fi AND :ff
                   AND estatus_flujo = 'AUTORIZADA'
                """
            ),
            {"emp": pre.empresa_id, "fi": pre.fecha_inicio, "ff": pre.fecha_fin},
        )
    else:
        await db.execute(
            text("UPDATE prenomina_semanal SET estatus = :est WHERE id = CAST(:id AS uuid)"),
            {"est": data.nuevo_estatus, "id": pid},
        )
        if data.nuevo_estatus in ("EXPORTADA", "RECIBIDA"):
            prev_cap = "PAGABLE" if data.nuevo_estatus == "EXPORTADA" else "EXPORTADA"
            await db.execute(
                text(
                    """
                    UPDATE campo_capturas_cosecha
                       SET estatus_flujo = :nest
                     WHERE empresa_id = :emp
                       AND fecha BETWEEN :fi AND :ff
                       AND estatus_flujo = :prev
                    """
                ),
                {"nest": data.nuevo_estatus, "emp": pre.empresa_id, "fi": pre.fecha_inicio, "ff": pre.fecha_fin, "prev": prev_cap},
            )

    await registrar_auditoria(
        db,
        actor,
        modulo="prenomina",
        accion=f"PRENOMINA_{data.nuevo_estatus}",
        tipo_entidad="PRENOMINA_SEMANAL",
        id_entidad=pid,
        empresa_id=pre.empresa_id,
        datos_antes={"estatus": pre.estatus},
        datos_despues={"estatus": data.nuevo_estatus, "hash_cierre_inmutable": hash_inm},
    )
    await db.commit()
    return {"prenomina_id": pid, "estatus": data.nuevo_estatus, "hash_cierre_inmutable": hash_inm}


@router.get("/semanal/{prenomina_id}")
async def consultar_prenomina_semanal_separada(
    prenomina_id: str,
    actor: AuthenticatedActor = Depends(require_permission("prenomina.calcular", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    pid = _uuid(prenomina_id, "Prenómina semanal")
    pre = (
        await db.execute(
            text("SELECT * FROM prenomina_semanal WHERE id = CAST(:id AS uuid)"),
            {"id": pid},
        )
    ).first()
    if not pre:
        raise HTTPException(status_code=404, detail="Prenómina no encontrada.")
    assert_scope(actor, "prenomina.calcular", empresa_id=pre.empresa_id, min_level=3)

    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT * FROM prenomina_semanal_detalle
                WHERE prenomina_semanal_id = CAST(:id AS uuid)
                ORDER BY circuito_pago, numero_empleado
                """
            ),
            {"id": pid},
        )
    ]
    return {
        "cabecera": dict(pre._mapping),
        "imss_merqry": [r for r in rows if r["circuito_pago"] == "IMSS_MERQRY"],
        "especial_contabilidad": [r for r in rows if r["circuito_pago"] == "ESPECIAL_CONTABILIDAD"],
    }
