from datetime import date
from decimal import Decimal
import json
import uuid
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth_usuarios.router import router as auth_router
from app.modules.core_org.router import router as org_router
from app.modules.documentos.router import router as docs_router
from app.modules.identidad.router import router as identidad_router
from app.modules.operacion_campo.router import router as campo_router
from app.modules.sync_offline.router import router as sync_router
from app.modules.trasplante_recepcion.router import router as trasplante_router
from app.services.pagos_service import MotorPagosCampo
from app.services.psicometria_service import MotorPsicometrico

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(org_router)
app.include_router(docs_router)
app.include_router(identidad_router)
app.include_router(sync_router)
app.include_router(campo_router)
app.include_router(trasplante_router)


class PostulacionIn(BaseModel):
    puesto_id: int
    curp: str
    nombre: str
    apellido_paterno: str
    apellido_materno: Optional[str] = None
    telefono: str
    email: Optional[str] = None
    fecha_nacimiento: date
    municipio_residencia: Optional[str] = None
    ruta_transporte_requerida: Optional[str] = None


class EvaluacionIn(BaseModel):
    candidato_id: str
    bateria_id: int
    respuestas: Dict[str, Any]
    tiempo_utilizado_segundos: int = 120


class ContratarIn(BaseModel):
    candidato_id: str
    numero_empleado: str
    salario_diario_pactado: float
    esquema_pago: str = "MIXTO"
    firma_acuse_base64: str = "FIRMA_DIGITAL_VALIDADA"


class RegistroCosechaIn(BaseModel):
    codigo_trazabilidad_caja: str
    empleado_qr_o_numero: str
    supervisor_numero: str = "EMP-1001"
    lote_id: int
    cantidad_cajas: float = 1.0
    calidad_fruta: str = "EXPORTACION"


def _parse_uuid_or_404(raw_id: str, entity_name: str) -> str:
    try:
        return str(uuid.UUID(raw_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail=f"{entity_name} {raw_id} no encontrado.")


@app.get("/api/v1/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("SELECT COUNT(*) FROM cultivos WHERE activo = TRUE"))
    env_res = await db.execute(text("SELECT db_environment FROM app_db_metadata WHERE id = 1"))
    return {
        "status": "online",
        "cultivos_activos": res.scalar(),
        "db_environment": env_res.scalar(),
        "merqry_mode": "READ_ONLY" if settings.merqry_readonly_mode else "INVALID",
    }


@app.get("/api/v1/catalogos/operacion")
async def catalogos_operacion(db: AsyncSession = Depends(get_db)):
    lotes = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT
                    l.id, l.codigo_lote, l.nombre_sector, l.empresa_clave,
                    l.variedad, l.superficie_ha, l.tipo_estructura,
                    l.nivel_tecnologia, l.origen_diseno, l.ancho_tunel_m,
                    l.estatus_fitosanitario, c.nombre AS cultivo, r.nombre AS rancho
                FROM lotes_produccion l
                JOIN cultivos c ON l.cultivo_id = c.id
                JOIN ranchos r ON l.rancho_id = r.id
                WHERE l.activo = TRUE
                ORDER BY l.id
                """
            )
        )
    ]
    empleados = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT
                    e.id, e.numero_empleado, e.merqry_employee_id,
                    e.nombre || ' ' || e.apellido_paterno AS nombre_completo,
                    p.titulo AS puesto, e.induccion_inocuidad_completada, e.esquema_pago
                FROM empleados e
                JOIN puestos p ON e.puesto_id = p.id
                WHERE e.estatus = 'ACTIVO'
                ORDER BY e.numero_empleado
                """
            )
        )
    ]
    return {"lotes": lotes, "empleados": empleados}


@app.get("/api/v1/public/vacantes")
async def listar_vacantes(db: AsyncSession = Depends(get_db)):
    q = text(
        """
        SELECT
            p.id, p.codigo_puesto, p.titulo, d.nombre AS departamento,
            t.nombre_nivel, t.tipo_pago_default, t.salario_minimo_diario,
            t.salario_maximo_diario, p.objetivo_puesto, p.vacantes_abiertas
        FROM puestos p
        JOIN departamentos d ON p.departamento_id = d.id
        JOIN tabulador_niveles t ON p.tabulador_id = t.id
        WHERE p.activo = TRUE AND p.publicar_en_landing = TRUE
        ORDER BY p.id
        """
    )
    return [dict(r._mapping) for r in await db.execute(q)]


@app.get("/api/v1/public/puesto/{puesto_id}/bateria")
async def obtener_bateria_puesto(puesto_id: int, db: AsyncSession = Depends(get_db)):
    bat = (
        await db.execute(
            text(
                """
                SELECT b.*
                FROM baterias_evaluacion b
                JOIN puesto_baterias pb ON b.id = pb.bateria_id
                WHERE pb.puesto_id = :pid
                LIMIT 1
                """
            ),
            {"pid": puesto_id},
        )
    ).first()
    if not bat:
        raise HTTPException(status_code=404, detail="Sin batería")
    return dict(bat._mapping)


@app.post("/api/v1/public/postular")
async def postular(data: PostulacionIn, db: AsyncSession = Depends(get_db)):
    curp = data.curp.strip().upper()
    kpi = (
        await db.execute(
            text(
                """
                SELECT dias_trabajados, promedio_cajas_dia, porcentaje_calidad_exportacion, clasificacion_recontratacion
                FROM vw_kpi_rendimiento_trabajador
                WHERE curp = :c
                """
            ),
            {"c": curp},
        )
    ).first()
    alerta = (
        f"REINGRESO ({kpi.clasificacion_recontratacion}): {kpi.dias_trabajados} días, {kpi.promedio_cajas_dia} cajas/día"
        if kpi
        else None
    )
    res = (
        await db.execute(
            text(
                """
                INSERT INTO candidatos (
                    puesto_id, curp, nombre, apellido_paterno, apellido_materno,
                    telefono, email, fecha_nacimiento, municipio_residencia,
                    ruta_transporte_requerida, es_reingreso, alerta_historial_kpi
                ) VALUES (
                    :pid, :curp, :nom, :ap, :am, :tel, :em, :fn, :mun, :rut, :rei, :ale
                )
                RETURNING id, nombre, apellido_paterno, es_reingreso, alerta_historial_kpi
                """
            ),
            {
                "pid": data.puesto_id,
                "curp": curp,
                "nom": data.nombre,
                "ap": data.apellido_paterno,
                "am": data.apellido_materno,
                "tel": data.telefono,
                "em": data.email,
                "fn": data.fecha_nacimiento,
                "mun": data.municipio_residencia,
                "rut": data.ruta_transporte_requerida,
                "rei": bool(kpi),
                "ale": alerta,
            },
        )
    ).first()
    await db.commit()
    return {"mensaje": "Postulación registrada", "candidato": dict(res._mapping)}


@app.post("/api/v1/public/evaluar")
async def evaluar_candidato(data: EvaluacionIn, db: AsyncSession = Depends(get_db)):
    candidato_uuid = _parse_uuid_or_404(data.candidato_id, "Candidato")

    bat = (
        await db.execute(
            text("SELECT codigo FROM baterias_evaluacion WHERE id = :bid"),
            {"bid": data.bateria_id},
        )
    ).first()
    if not bat:
        raise HTTPException(
            status_code=404,
            detail=f"Batería de evaluación {data.bateria_id} no encontrada.",
        )

    cand = (
        await db.execute(
            text("SELECT id FROM candidatos WHERE id = :cid"),
            {"cid": candidato_uuid},
        )
    ).first()
    if not cand:
        raise HTTPException(
            status_code=404,
            detail=f"Candidato {data.candidato_id} no encontrado.",
        )

    resultado = MotorPsicometrico.evaluar_bateria(bat.codigo, data.respuestas)
    await db.execute(
        text(
            """
            INSERT INTO resultados_evaluaciones (
                candidato_id, bateria_id, respuestas_json, puntaje_obtenido,
                interpretacion_automatica, tiempo_utilizado_segundos
            ) VALUES (
                :cid, :bid, :resp, :pts, :interp, :t
            )
            ON CONFLICT (candidato_id, bateria_id) DO UPDATE SET
                respuestas_json = EXCLUDED.respuestas_json,
                puntaje_obtenido = EXCLUDED.puntaje_obtenido,
                interpretacion_automatica = EXCLUDED.interpretacion_automatica,
                tiempo_utilizado_segundos = EXCLUDED.tiempo_utilizado_segundos
            """
        ),
        {
            "cid": candidato_uuid,
            "bid": data.bateria_id,
            "resp": json.dumps(data.respuestas),
            "pts": resultado["puntaje"],
            "interp": json.dumps(resultado),
            "t": data.tiempo_utilizado_segundos,
        },
    )
    est = "APROBADO_RH" if resultado["puntaje"] >= 70 else "EN_EVALUACION"
    await db.execute(
        text("UPDATE candidatos SET score_global = :pts, estatus = :est WHERE id = :cid"),
        {"pts": resultado["puntaje"], "est": est, "cid": candidato_uuid},
    )
    await db.commit()
    return {"resultado": resultado, "estatus_candidato": est}


@app.get("/api/v1/rh/candidatos")
async def listar_candidatos_rh(db: AsyncSession = Depends(get_db)):
    return [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT c.*, p.titulo AS puesto_titulo
                FROM candidatos c
                JOIN puestos p ON c.puesto_id = p.id
                ORDER BY c.creado_en DESC
                """
            )
        )
    ]


@app.post("/api/v1/rh/contratar")
async def contratar_candidato(data: ContratarIn, db: AsyncSession = Depends(get_db)):
    candidato_uuid = _parse_uuid_or_404(data.candidato_id, "Candidato")

    cand = (
        await db.execute(
            text("SELECT * FROM candidatos WHERE id = :cid"),
            {"cid": candidato_uuid},
        )
    ).first()
    if not cand:
        raise HTTPException(
            status_code=404,
            detail=f"Candidato {data.candidato_id} no encontrado.",
        )

    emp = (
        await db.execute(
            text(
                """
                INSERT INTO empleados (
                    numero_empleado, candidato_origen_id, puesto_id, curp, nombre,
                    apellido_paterno, apellido_materno, fecha_ingreso, tipo_contrato,
                    salario_diario_pactado, esquema_pago, induccion_inocuidad_completada,
                    fecha_induccion_inocuidad, codigo_qr_hash
                ) VALUES (
                    :num, :cid, :pid, :curp, :nom, :ap, :am, CURRENT_DATE, 'TEMPORADA',
                    :sal, :esq, TRUE, CURRENT_DATE, :qr
                )
                RETURNING id, numero_empleado
                """
            ),
            {
                "num": data.numero_empleado,
                "cid": cand.id,
                "pid": cand.puesto_id,
                "curp": cand.curp,
                "nom": cand.nombre,
                "ap": cand.apellido_paterno,
                "am": cand.apellido_materno,
                "sal": data.salario_diario_pactado,
                "esq": data.esquema_pago,
                "qr": f"QR-{data.numero_empleado}",
            },
        )
    ).first()
    await db.execute(
        text("UPDATE candidatos SET estatus = 'CONTRATADO' WHERE id = :cid"),
        {"cid": cand.id},
    )
    await db.commit()
    return {"mensaje": "Empleado dado de alta", "empleado": dict(emp._mapping)}


@app.get("/api/v1/rh/prenomina")
async def consultar_prenomina(db: AsyncSession = Depends(get_db)):
    return [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT
                    pd.*, e.numero_empleado, e.merqry_employee_id,
                    e.nombre || ' ' || e.apellido_paterno AS empleado, e.esquema_pago
                FROM prenomina_diaria pd
                JOIN empleados e ON pd.empleado_id = e.id
                ORDER BY pd.fecha DESC
                """
            )
        )
    ]


@app.post("/api/v1/campo/cosecha")
async def registrar_cosecha_tablet(data: RegistroCosechaIn, db: AsyncSession = Depends(get_db)):
    emp = (
        await db.execute(
            text(
                """
                SELECT id, estatus, induccion_inocuidad_completada
                FROM empleados
                WHERE numero_empleado = :cod OR codigo_qr_hash = :cod
                """
            ),
            {"cod": data.empleado_qr_o_numero},
        )
    ).first()
    if not emp or emp.estatus != "ACTIVO":
        raise HTTPException(status_code=400, detail="Trabajador no encontrado o inactivo.")
    if not emp.induccion_inocuidad_completada:
        raise HTTPException(status_code=403, detail="BLOQUEO INOCUIDAD: Sin inducción BPA.")

    sup = (
        await db.execute(
            text("SELECT id FROM empleados WHERE numero_empleado = :s LIMIT 1"),
            {"s": data.supervisor_numero},
        )
    ).first()

    lote = (
        await db.execute(
            text(
                """
                SELECT l.id, l.cultivo_id, l.estatus_fitosanitario, c.peso_neto_caja_kg
                FROM lotes_produccion l
                JOIN cultivos c ON l.cultivo_id = c.id
                WHERE l.id = :lid AND l.activo = TRUE
                """
            ),
            {"lid": data.lote_id},
        )
    ).first()
    if not lote or lote.estatus_fitosanitario != "LIBRE_CORTE":
        raise HTTPException(status_code=403, detail="BLOQUEO FITOSANITARIO EN LOTE")

    regla = (
        await db.execute(
            text(
                """
                SELECT r.*
                FROM reglas_pago_tarifas r
                JOIN catalogo_labores cl ON r.labor_id = cl.id
                WHERE cl.codigo = 'COSECHA' AND r.cultivo_id = :cid AND r.activa = TRUE
                LIMIT 1
                """
            ),
            {"cid": lote.cultivo_id},
        )
    ).first()
    if not regla:
        raise HTTPException(
            status_code=400,
            detail="Sin regla de pago activa para cosecha en este cultivo.",
        )

    hoy = date.today()
    jid = (
        await db.execute(
            text(
                """
                INSERT INTO jornadas_diarias (fecha, empleado_id, supervisor_id, rancho_id, hora_entrada)
                SELECT :hoy, :eid, :sid, rancho_id, NOW()
                FROM lotes_produccion
                WHERE id = :lid
                ON CONFLICT (fecha, empleado_id) DO UPDATE SET estatus_asistencia = 'PRESENTE'
                RETURNING id
                """
            ),
            {"hoy": hoy, "eid": emp.id, "sid": sup.id if sup else emp.id, "lid": data.lote_id},
        )
    ).scalar()

    folio_qr = data.codigo_trazabilidad_caja.strip() or f"BOX-{uuid.uuid4().hex[:8].upper()}"
    await db.execute(
        text(
            """
            INSERT INTO registros_cosecha (
                codigo_trazabilidad_caja, jornada_id, empleado_id, lote_id,
                cultivo_id, regla_pago_id, cantidad_cajas, peso_kg_calculado, calidad_fruta
            ) VALUES (
                :qr, :jid, :eid, :lid, :cid, :rid, :cajas, :peso, :cal
            )
            """
        ),
        {
            "qr": folio_qr,
            "jid": jid,
            "eid": emp.id,
            "lid": data.lote_id,
            "cid": lote.cultivo_id,
            "rid": regla.id,
            "cajas": data.cantidad_cajas,
            "peso": Decimal(str(data.cantidad_cajas)) * Decimal(str(lote.peso_neto_caja_kg)),
            "cal": data.calidad_fruta,
        },
    )

    tot = (
        await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN calidad_fruta = 'EXPORTACION' THEN cantidad_cajas ELSE 0 END), 0) AS exp,
                    COALESCE(SUM(CASE WHEN calidad_fruta = 'NACIONAL' THEN cantidad_cajas ELSE 0 END), 0) AS nac,
                    COALESCE(SUM(CASE WHEN calidad_fruta = 'PROCESO_REZAGA' THEN cantidad_cajas ELSE 0 END), 0) AS rez
                FROM registros_cosecha
                WHERE jornada_id = :jid
                """
            ),
            {"jid": jid},
        )
    ).first()

    cajas_exp = Decimal(str(tot.exp))
    cajas_nac = Decimal(str(tot.nac))
    cajas_rez = Decimal(str(tot.rez))

    calc = MotorPagosCampo.calcular_pago_diario(
        dict(regla._mapping),
        cajas_exp,
        cajas_nac,
        cajas_rez,
    )

    await db.execute(
        text(
            """
            INSERT INTO prenomina_diaria (
                fecha, empleado_id, total_cajas_exportacion, total_cajas_rezaga,
                porcentaje_rezaga, pago_jornal_base, pago_destajo, pago_bono_calidad
            ) VALUES (
                :hoy, :eid, :cexp, :crez, :pct, :jor, :des, :bon
            )
            ON CONFLICT (fecha, empleado_id) DO UPDATE SET
                total_cajas_exportacion = EXCLUDED.total_cajas_exportacion,
                total_cajas_rezaga = EXCLUDED.total_cajas_rezaga,
                porcentaje_rezaga = EXCLUDED.porcentaje_rezaga,
                pago_jornal_base = EXCLUDED.pago_jornal_base,
                pago_destajo = EXCLUDED.pago_destajo,
                pago_bono_calidad = EXCLUDED.pago_bono_calidad,
                calculado_en = NOW()
            """
        ),
        {
            "hoy": hoy,
            "eid": emp.id,
            "cexp": cajas_exp,
            "crez": cajas_rez,
            "pct": calc["porcentaje_rezaga"],
            "jor": calc["pago_jornal_base"],
            "des": calc["pago_destajo"],
            "bon": calc["pago_bono_calidad"],
        },
    )
    await db.commit()
    return {"status": "OK", "caja": folio_qr, "acumulado_hoy": calc}


@app.get("/api/v1/direccion/dashboard")
async def dashboard_direccion(db: AsyncSession = Depends(get_db)):
    cultivos = [
        dict(r._mapping)
        for r in await db.execute(text("SELECT * FROM vw_direccion_rentabilidad_cultivo"))
    ]
    kpis = [
        dict(r._mapping)
        for r in await db.execute(
            text("SELECT * FROM vw_kpi_rendimiento_trabajador ORDER BY total_cajas_cosechadas DESC")
        )
    ]
    return {"cultivos": cultivos, "kpis_personal": kpis}
