"""Motor de conciliacion multi-etapa, hashes SHA-256 de integridad y calculo presupuestal (Fase 4)."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def compute_conciliacion_hash(snapshot_core: Dict[str, Any]) -> str:
    canonical = json.dumps(snapshot_core, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _q2(val: Any) -> Decimal:
    return Decimal(str(val or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(val: Any) -> Decimal:
    return Decimal(str(val or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


async def calcular_conciliacion_operativa(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha_inicio: date,
    fecha_fin: date,
) -> Dict[str, Any]:
    """
    Cruza en tiempo real las 4 fuentes operativas de PostgreSQL para (empresa_id, fecha_inicio..fecha_fin):
      1. Cosecha de campo (`campo_capturas_cosecha`)
      2. Traslados de cajas a empaque (`campo_traslados_cajas`)
      3. Prenomina semanal (`prenomina_semanal` / `prenomina_semanal_detalle`) separada IMSS vs ESPECIAL
      4. Aplicaciones fitosanitarias (`aplicaciones_fitosanitarias`) + gastos (`fin_gastos_operativos`)
    """
    campo = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_capturas,
                    COALESCE(SUM(cajas_exportacion), 0) AS cajas_exp,
                    COALESCE(SUM(cajas_nacional), 0) AS cajas_nac,
                    COALESCE(SUM(cajas_merma_rezaga), 0) AS cajas_merma,
                    COALESCE(SUM(CASE WHEN alerta_merma_7pct THEN 1 ELSE 0 END), 0) AS alertas_merma,
                    COALESCE(SUM(CASE WHEN estatus_flujo IN ('AUTORIZADA', 'PAGABLE', 'EXPORTADA', 'RECIBIDA') THEN 1 ELSE 0 END), 0) AS capturas_autorizadas
                FROM campo_capturas_cosecha
                WHERE empresa_id = :emp
                  AND fecha BETWEEN :fi AND :ff
                """
            ),
            {"emp": empresa_id, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ).mappings().first()

    empaque = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_remisiones,
                    COALESCE(SUM(cantidad_cajas), 0) AS cajas_trasladadas,
                    COALESCE(SUM(CASE WHEN estatus_traslado IN ('RECEPCION_EMPAQUE', 'EMPACADO', 'DESPACHO') THEN cantidad_cajas ELSE 0 END), 0) AS cajas_recibidas_empaque
                FROM campo_traslados_cajas
                WHERE empresa_id = :emp
                  AND fecha BETWEEN :fi AND :ff
                """
            ),
            {"emp": empresa_id, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ).mappings().first()

    # Mano de obra desde prenomina semanal solapada en el rango (separada por circuito)
    nomina = (
        await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(total_imss_merqry), 0) AS mo_imss_semanal,
                    COALESCE(SUM(total_especial_contabilidad), 0) AS mo_especial_semanal,
                    COUNT(*) AS semanas_incluidas
                FROM prenomina_semanal
                WHERE empresa_id = :emp
                  AND fecha_inicio <= :ff
                  AND fecha_fin >= :fi
                """
            ),
            {"emp": empresa_id, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ).mappings().first()

    # Insumos fitosanitarios aplicados en lotes de la empresa (filtrando por clave de empresa)
    fito = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS aplicaciones_count,
                    COALESCE(SUM(af.costo_total_aplicacion), 0) AS costo_fito
                FROM aplicaciones_fitosanitarias af
                JOIN lotes_produccion lp ON lp.id = af.lote_id
                JOIN empresas e ON e.clave = lp.empresa_clave
                WHERE e.id = :emp
                  AND af.fecha_aplicacion::date BETWEEN :fi AND :ff
                """
            ),
            {"emp": empresa_id, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ).mappings().first()

    # Gastos operativos devengados en fin_gastos_operativos (respetando circuito)
    gastos_rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT rubro, circuito_origen, COALESCE(SUM(monto), 0) AS total
                FROM fin_gastos_operativos
                WHERE empresa_id = :emp
                  AND fecha BETWEEN :fi AND :ff
                GROUP BY rubro, circuito_origen
                ORDER BY rubro, circuito_origen
                """
            ),
            {"emp": empresa_id, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ]

    gasto_mo_imss = Decimal("0")
    gasto_mo_esp = Decimal("0")
    gasto_fito_extra = Decimal("0")
    gasto_otros = Decimal("0")
    for g in gastos_rows:
        amt = _q2(g["total"])
        if g["rubro"] == "MANO_OBRA_IMSS":
            gasto_mo_imss += amt
        elif g["rubro"] == "MANO_OBRA_ESPECIAL":
            gasto_mo_esp += amt
        elif g["rubro"] == "INSUMOS_FITO":
            gasto_fito_extra += amt
        else:
            gasto_otros += amt

    cajas_exp = _q2(campo["cajas_exp"])
    cajas_nac = _q2(campo["cajas_nac"])
    cajas_merma = _q2(campo["cajas_merma"])
    cajas_comerciales_campo = cajas_exp + cajas_nac
    cajas_trasladadas = _q2(empaque["cajas_trasladadas"])
    delta_cajas = _q2(cajas_comerciales_campo - cajas_trasladadas)

    total_mo_imss = _q2(_q2(nomina["mo_imss_semanal"]) + gasto_mo_imss)
    total_mo_esp = _q2(_q2(nomina["mo_especial_semanal"]) + gasto_mo_esp)
    total_fito = _q2(_q2(fito["costo_fito"]) + gasto_fito_extra)
    total_otros = _q2(gasto_otros)
    costo_total = _q2(total_mo_imss + total_mo_esp + total_fito + total_otros)

    total_mo = total_mo_imss + total_mo_esp
    costo_mo_caja = _q4(total_mo / cajas_exp) if cajas_exp > Decimal("0") else Decimal("0.0000")

    core = {
        "empresa_id": empresa_id,
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "cajas_campo_exportacion": str(cajas_exp),
        "cajas_campo_nacional": str(cajas_nac),
        "cajas_campo_merma": str(cajas_merma),
        "cajas_trasladadas_empaque": str(cajas_trasladadas),
        "delta_cajas_campo_vs_empaque": str(delta_cajas),
        "total_mo_imss_merqry": str(total_mo_imss),
        "total_mo_especial_contabilidad": str(total_mo_esp),
        "total_insumos_fito": str(total_fito),
        "total_otros_gastos": str(total_otros),
        "costo_total_directo": str(costo_total),
        "costo_mo_por_caja_exportable": str(costo_mo_caja),
    }
    hash_sha256 = compute_conciliacion_hash(core)

    detalle = {
        "campo": {
            "total_capturas": int(campo["total_capturas"]),
            "capturas_autorizadas": int(campo["capturas_autorizadas"]),
            "alertas_merma_7pct": int(campo["alertas_merma"]),
        },
        "empaque": {
            "total_remisiones": int(empaque["total_remisiones"]),
            "cajas_recibidas_empaque": float(_q2(empaque["cajas_recibidas_empaque"])),
            "alerta_brecha_cajas": delta_cajas != Decimal("0.00"),
        },
        "nomina": {
            "semanas_incluidas": int(nomina["semanas_incluidas"]),
            "imss_merqry_semanal": float(_q2(nomina["mo_imss_semanal"])),
            "especial_contabilidad_semanal": float(_q2(nomina["mo_especial_semanal"])),
        },
        "fitosanitario": {
            "aplicaciones_count": int(fito["aplicaciones_count"]),
            "costo_aplicaciones": float(_q2(fito["costo_fito"])),
        },
        "gastos_por_rubro": [
            {
                "rubro": g["rubro"],
                "circuito_origen": g["circuito_origen"],
                "total": float(_q2(g["total"])),
            }
            for g in gastos_rows
        ],
    }

    return {
        "core": core,
        "detalle": detalle,
        "hash_conciliacion_sha256": hash_sha256,
        "numerics": {
            "cajas_exp": cajas_exp,
            "cajas_nac": cajas_nac,
            "cajas_merma": cajas_merma,
            "cajas_trasladadas": cajas_trasladadas,
            "delta_cajas": delta_cajas,
            "total_mo_imss": total_mo_imss,
            "total_mo_esp": total_mo_esp,
            "total_fito": total_fito,
            "total_otros": total_otros,
            "costo_total": costo_total,
            "costo_mo_caja": costo_mo_caja,
        },
    }
