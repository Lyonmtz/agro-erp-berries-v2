import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://agro_admin:DevPassword2026!@db:5432/agro_berries_erp"
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

from typing import Dict, Any

class MotorPsicometrico:
    @staticmethod
    def evaluar_bateria(codigo_bateria: str, respuestas: Dict[str, Any]) -> Dict[str, Any]:
        if codigo_bateria == "ZAVIC_OP":
            puntajes = {"moralidad": 0, "legalidad": 0, "compromiso": 0, "apego_normas": 0}
            for _, val in respuestas.items():
                dim = val.get("dimension")
                pts = float(val.get("puntos", 0))
                if dim in puntajes:
                    puntajes[dim] += pts
            promedio = round(sum(puntajes.values()) / max(len(puntajes), 1), 2)
            dictamen = "APTO_OPERATIVO" if promedio >= 70 and puntajes["legalidad"] >= 65 else "REVISION_RH"
            return {"puntaje": promedio, "dimensiones": puntajes, "dictamen": dictamen}

        elif codigo_bateria == "CLEAVER_SUP":
            disc = {"D": 0, "I": 0, "S": 0, "C": 0}
            for _, val in respuestas.items():
                mas = val.get("mas")
                menos = val.get("menos")
                if mas in disc: disc[mas] += 10
                if menos in disc: disc[menos] -= 5
            score = min(100.0, max(0.0, 50 + (disc["D"] + disc["C"]) * 0.8))
            dictamen = "LIDER_OPERATIVO_APTO" if score >= 70 else "BAJO_EMPUJE_CONTROL"
            return {"puntaje": round(score, 2), "perfil_disc": disc, "dictamen": dictamen}

        else:
            total_obtenido = sum(float(v.get("puntos", 0)) for v in respuestas.values())
            total_maximo = sum(float(v.get("max_puntos", 10)) for v in respuestas.values()) or 1
            porcentaje = round((total_obtenido / total_maximo) * 100, 2)
            return {
                "puntaje": porcentaje,
                "dictamen": "APROBADO" if porcentaje >= 75 else "NO_APROBADO"
            }

from decimal import Decimal
from typing import Dict

class MotorPagosCampo:
    @staticmethod
    def calcular_pago_diario(
        regla: Dict,
        cajas_exportacion: Decimal,
        cajas_nacional: Decimal,
        cajas_rezaga: Decimal,
        unidades_labor_cultural: Decimal = Decimal("0")
    ) -> Dict[str, Decimal]:
        total_cajas = cajas_exportacion + cajas_nacional + cajas_rezaga
        porcentaje_rezaga = (
            (cajas_rezaga * Decimal("100") / total_cajas) if total_cajas > 0 else Decimal("0")
        )

        modalidad = regla["modalidad_pago"]
        jornal_base = Decimal(str(regla["tarifa_jornal_base"]))
        tarifa_unidad = Decimal(str(regla["tarifa_por_unidad"]))
        meta_minima = Decimal(str(regla["meta_minima_unidades"]))
        tarifa_excedente = Decimal(str(regla["tarifa_excedente_unidad"]))
        max_rezaga = Decimal(str(regla["porcentaje_rezaga_maximo"]))
        bono_unidad = Decimal(str(regla["bono_calidad_por_unidad"]))

        pago_jornal = Decimal("0.00")
        pago_destajo = Decimal("0.00")
        pago_bono = Decimal("0.00")

        unidades_totales = total_cajas if total_cajas > 0 else unidades_labor_cultural

        if modalidad == "JORNAL_PURO":
            pago_jornal = jornal_base
        elif modalidad == "DESTAJO_PURO":
            pago_destajo = unidades_totales * tarifa_unidad
        elif modalidad == "MIXTO_GARANTIA":
            pago_jornal = jornal_base
            if unidades_totales > meta_minima:
                excedente = unidades_totales - meta_minima
                pago_destajo = excedente * tarifa_excedente

        if total_cajas > 0 and porcentaje_rezaga <= max_rezaga and bono_unidad > 0:
            pago_bono = cajas_exportacion * bono_unidad

        return {
            "total_cajas": round(total_cajas, 2),
            "porcentaje_rezaga": round(porcentaje_rezaga, 2),
            "pago_jornal_base": round(pago_jornal, 2),
            "pago_destajo": round(pago_destajo, 2),
            "pago_bono_calidad": round(pago_bono, 2),
            "total_percepcion_dia": round(pago_jornal + pago_destajo + pago_bono, 2)
        }

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import date
from decimal import Decimal

from app.core.database import get_db
from app.services.psicometria_service import MotorPsicometrico
from app.services.pagos_service import MotorPagosCampo

app = FastAPI(
    title="AGRO-ERP Berries (Frambuesa, Arándano, Fresa)",
    description="Sistema Integral de RH, Producción en Campo, Inocuidad, Costos y Exportación",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class RegistroCosechaIn(BaseModel):
    codigo_trazabilidad_caja: str
    empleado_qr_o_numero: str
    supervisor_id: str
    lote_id: int
    cantidad_cajas: float = 1.0
    calidad_fruta: str = "EXPORTACION"

@app.get("/api/v1/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("SELECT COUNT(*) FROM cultivos"))
    return {"status": "online", "cultivos_activos": res.scalar()}

@app.get("/api/v1/public/vacantes")
async def listar_vacantes_landing(db: AsyncSession = Depends(get_db)):
    query = text("""
        SELECT p.id, p.codigo_puesto, p.titulo, d.nombre AS departamento,
               t.nombre_nivel, t.tipo_pago_default, t.salario_minimo_diario, t.salario_maximo_diario,
               p.objetivo_puesto, p.requisitos_perfil, p.vacantes_abiertas
        FROM puestos p
        JOIN departamentos d ON p.departamento_id = d.id
        JOIN tabulador_niveles t ON p.tabulador_id = t.id
        WHERE p.activo = TRUE AND p.publicar_en_landing = TRUE AND p.vacantes_abiertas > 0
    """)
    result = await db.execute(query)
    return [dict(row._mapping) for row in result]

@app.post("/api/v1/public/postular")
async def registrar_postulacion(data: PostulacionIn, db: AsyncSession = Depends(get_db)):
    curp_limpia = data.curp.strip().upper()
    kpi_query = text("""
        SELECT dias_trabajados, total_cajas_cosechadas, promedio_cajas_dia,
               porcentaje_calidad_exportacion, clasificacion_recontratacion
        FROM vw_kpi_rendimiento_trabajador
        WHERE curp = :curp
    """)
    kpi_res = (await db.execute(kpi_query, {"curp": curp_limpia})).first()
    
    es_reingreso = False
    alerta_kpi = None
    if kpi_res:
        es_reingreso = True
        alerta_kpi = (
            f"REINGRESO ({kpi_res.clasificacion_recontratacion}): "
            f"{kpi_res.dias_trabajados} días trabajados, promedio {kpi_res.promedio_cajas_dia} cajas/día, "
            f"{kpi_res.porcentaje_calidad_exportacion}% calidad exportación."
        )

    insert_q = text("""
        INSERT INTO candidatos (
            puesto_id, curp, nombre, apellido_paterno, apellido_materno,
            telefono, email, fecha_nacimiento, municipio_residencia,
            ruta_transporte_requerida, es_reingreso, alerta_historial_kpi
        ) VALUES (
            :puesto_id, :curp, :nombre, :ap_pat, :ap_mat,
            :tel, :email, :fnac, :muni, :ruta, :reingreso, :alerta
        ) RETURNING id, es_reingreso, alerta_historial_kpi
    """)
    nuevo = (await db.execute(insert_q, {
        "puesto_id": data.puesto_id, "curp": curp_limpia, "nombre": data.nombre,
        "ap_pat": data.apellido_paterno, "ap_mat": data.apellido_materno,
        "tel": data.telefono, "email": data.email, "fnac": data.fecha_nacimiento,
        "muni": data.municipio_residencia, "ruta": data.ruta_transporte_requerida,
        "reingreso": es_reingreso, "alerta": alerta_kpi
    })).first()
    await db.commit()
    return {"mensaje": "Postulación registrada", "candidato": dict(nuevo._mapping)}

@app.post("/api/v1/campo/cosecha")
async def registrar_cosecha_tablet(data: RegistroCosechaIn, db: AsyncSession = Depends(get_db)):
    emp_q = text("""
        SELECT id, numero_empleado, estatus, induccion_inocuidad_completada
        FROM empleados WHERE numero_empleado = :cod OR codigo_qr_hash = :cod
    """)
    emp = (await db.execute(emp_q, {"cod": data.empleado_qr_o_numero})).first()
    if not emp or emp.estatus != "ACTIVO":
        raise HTTPException(status_code=400, detail="Trabajador no encontrado o inactivo.")
    if not emp.induccion_inocuidad_completada:
        raise HTTPException(status_code=403, detail="BLOQUEO INOCUIDAD: Trabajador sin inducción BPA completada.")

    lote_q = text("""
        SELECT l.id, l.cultivo_id, l.estatus_fitosanitario, l.fecha_liberacion_corte, c.peso_neto_caja_kg
        FROM lotes_produccion l
        JOIN cultivos c ON l.cultivo_id = c.id
        WHERE l.id = :lote_id AND l.activo = TRUE
    """)
    lote = (await db.execute(lote_q, {"lote_id": data.lote_id})).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado.")
    if lote.estatus_fitosanitario != "LIBRE_CORTE":
        raise HTTPException(
            status_code=403,
            detail=f"BLOQUEO FITOSANITARIO: Lote en estado {lote.estatus_fitosanitario}. Liberación: {lote.fecha_liberacion_corte}"
        )

    regla_q = text("""
        SELECT r.* FROM reglas_pago_tarifas r
        JOIN catalogo_labores cl ON r.labor_id = cl.id
        WHERE cl.codigo = 'COSECHA' AND r.cultivo_id = :cultivo_id AND r.activa = TRUE
        ORDER BY r.fecha_inicio_vigencia DESC LIMIT 1
    """)
    regla = (await db.execute(regla_q, {"cultivo_id": lote.cultivo_id})).first()
    if not regla:
        raise HTTPException(status_code=400, detail="No existe tarifa de cosecha activa para este cultivo.")

    hoy = date.today()
    jornada_q = text("""
        INSERT INTO jornadas_diarias (fecha, empleado_id, supervisor_id, rancho_id, hora_entrada)
        SELECT :hoy, :emp_id, :sup_id, rancho_id, NOW()
        FROM lotes_produccion WHERE id = :lote_id
        ON CONFLICT (fecha, empleado_id) DO UPDATE SET estatus_asistencia = 'PRESENTE'
        RETURNING id
    """)
    jornada_id = (await db.execute(jornada_q, {
        "hoy": hoy, "emp_id": emp.id, "sup_id": data.supervisor_id, "lote_id": data.lote_id
    })).scalar()

    peso_calc = Decimal(str(data.cantidad_cajas)) * Decimal(str(lote.peso_neto_caja_kg))
    ins_cosecha = text("""
        INSERT INTO registros_cosecha (
            codigo_trazabilidad_caja, jornada_id, empleado_id, lote_id,
            cultivo_id, regla_pago_id, cantidad_cajas, peso_kg_calculado, calidad_fruta
        ) VALUES (
            :qr_caja, :jornada_id, :emp_id, :lote_id,
            :cultivo_id, :regla_id, :cajas, :peso, :calidad
        )
    """)
    await db.execute(ins_cosecha, {
        "qr_caja": data.codigo_trazabilidad_caja, "jornada_id": jornada_id,
        "emp_id": emp.id, "lote_id": data.lote_id, "cultivo_id": lote.cultivo_id,
        "regla_id": regla.id, "cajas": data.cantidad_cajas,
        "peso": peso_calc, "calidad": data.calidad_fruta
    })

    totales_q = text("""
        SELECT
            COALESCE(SUM(CASE WHEN calidad_fruta = 'EXPORTACION' THEN cantidad_cajas ELSE 0 END), 0) AS exp,
            COALESCE(SUM(CASE WHEN calidad_fruta = 'NACIONAL' THEN cantidad_cajas ELSE 0 END), 0) AS nac,
            COALESCE(SUM(CASE WHEN calidad_fruta = 'PROCESO_REZAGA' THEN cantidad_cajas ELSE 0 END), 0) AS rez
        FROM registros_cosecha
        WHERE jornada_id = :jornada_id
    """)
    tot = (await db.execute(totales_q, {"jornada_id": jornada_id})).first()
    calculo = MotorPagosCampo.calcular_pago_diario(
        dict(regla._mapping), Decimal(str(tot.exp)), Decimal(str(tot.nac)), Decimal(str(tot.rez))
    )

    upsert_prenomina = text("""
        INSERT INTO prenomina_diaria (
            fecha, empleado_id, total_cajas_exportacion, total_cajas_rezaga,
            porcentaje_rezaga, pago_jornal_base, pago_destajo, pago_bono_calidad
        ) VALUES (
            :hoy, :emp_id, :cajas_exp, :cajas_rez, :pct_rez, :jornal, :destajo, :bono
        )
        ON CONFLICT (fecha, empleado_id) DO UPDATE SET
            total_cajas_exportacion = EXCLUDED.total_cajas_exportacion,
            total_cajas_rezaga = EXCLUDED.total_cajas_rezaga,
            porcentaje_rezaga = EXCLUDED.porcentaje_rezaga,
            pago_jornal_base = EXCLUDED.pago_jornal_base,
            pago_destajo = EXCLUDED.pago_destajo,
            pago_bono_calidad = EXCLUDED.pago_bono_calidad,
            calculado_en = NOW()
    """)
    await db.execute(upsert_prenomina, {
        "hoy": hoy, "emp_id": emp.id,
        "cajas_exp": calculo["total_cajas"], "cajas_rez": Decimal(str(tot.rez)),
        "pct_rez": calculo["porcentaje_rezaga"], "jornal": calculo["pago_jornal_base"],
        "destajo": calculo["pago_destajo"], "bono": calculo["pago_bono_calidad"]
    })

    await db.commit()
    return {
        "status": "OK",
        "caja": data.codigo_trazabilidad_caja,
        "acumulado_hoy": calculo
    }

docker compose up -d --build