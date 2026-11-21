from datetime import date
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import (
    AuthenticatedActor,
    assert_scope,
    filter_rows_by_scope,
    require_permission,
)
from app.modules.identidad.etl_service import ejecutar_etl_identidades

router = APIRouter(prefix="/api/v1/identidad", tags=["Identidad y Relaciones Laborales"])


class CrearPersonaIn(BaseModel):
    curp: Optional[str] = Field(default=None, min_length=18, max_length=18)
    rfc: Optional[str] = Field(default=None, max_length=13)
    nss: Optional[str] = Field(default=None, max_length=11)
    nombre: str = Field(..., min_length=2, max_length=100)
    apellido_paterno: str = Field(..., min_length=2, max_length=100)
    apellido_materno: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    municipio_residencia: Optional[str] = None
    empresa_id: int


class CrearRelacionLaboralIn(BaseModel):
    persona_id: str
    empresa_id: int
    sucursal_id: Optional[int] = None
    unidad_operativa_id: Optional[int] = None
    numero_empleado: str = Field(..., min_length=2, max_length=30)
    merqry_employee_id: Optional[str] = None
    circuito_pago: str = Field(default="IMSS_MERQRY", pattern="^(IMSS_MERQRY|ESPECIAL_CONTABILIDAD)$")
    puesto_nominal_id: int
    fecha_ingreso: date


class AsignarFuncionTemporalIn(BaseModel):
    relacion_laboral_id: str
    funcion_operativa: str
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    motivo: str = Field(..., min_length=4)
    unidad_operativa_id: Optional[int] = None


class EtlImportIn(BaseModel):
    fuente_nombre: str = Field(..., min_length=3, max_length=150)
    empresa_id: int
    sucursal_id: Optional[int] = None
    unidad_operativa_id: Optional[int] = None
    registros: List[Dict[str, Any]] = Field(..., min_length=1)


@router.get("/personas")
async def listar_personas(
    empresa_id: Optional[int] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("identidad.leer")),
    db: AsyncSession = Depends(get_db),
):
    where = "WHERE rl.empresa_id = :emp" if empresa_id is not None else ""
    params = {"emp": empresa_id} if empresa_id is not None else {}
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT
                    p.id::text AS id, p.curp, p.nombre, p.apellido_paterno, p.apellido_materno,
                    p.telefono, p.clave_interna_qr, p.activo,
                    rl.empresa_id, rl.sucursal_id, rl.unidad_operativa_id,
                    rl.numero_empleado, rl.circuito_pago, rl.puesto_nominal_id
                FROM personas p
                LEFT JOIN relaciones_laborales rl ON rl.persona_id = p.id
                {where}
                ORDER BY p.creado_en DESC
                """
            ),
            params,
        )
    ]
    return filter_rows_by_scope(rows, actor, "identidad.leer")


@router.post("/personas", status_code=status.HTTP_201_CREATED)
async def crear_persona(
    data: CrearPersonaIn,
    actor: AuthenticatedActor = Depends(require_permission("identidad.escribir", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(actor, "identidad.escribir", empresa_id=data.empresa_id, min_level=2)
    clave_qr = f"QR-PER-{uuid.uuid4().hex[:10].upper()}"
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO personas (
                        curp, rfc, nss, nombre, apellido_paterno, apellido_materno,
                        fecha_nacimiento, telefono, email, municipio_residencia, clave_interna_qr
                    ) VALUES (
                        :curp, :rfc, :nss, :nom, :ap, :am, :fn, :tel, :em, :mun, :qr
                    )
                    RETURNING id::text AS id, curp, nombre, apellido_paterno, apellido_materno, clave_interna_qr
                    """
                ),
                {
                    "curp": data.curp.strip().upper() if data.curp else None,
                    "rfc": data.rfc.strip().upper() if data.rfc else None,
                    "nss": data.nss.strip() if data.nss else None,
                    "nom": data.nombre.strip(),
                    "ap": data.apellido_paterno.strip(),
                    "am": data.apellido_materno.strip() if data.apellido_materno else None,
                    "fn": data.fecha_nacimiento,
                    "tel": data.telefono.strip() if data.telefono else None,
                    "em": data.email.strip().lower() if data.email else None,
                    "mun": data.municipio_residencia,
                    "qr": clave_qr,
                },
            )
        ).first()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="CURP, RFC o NSS ya registrado.") from exc

    await db.execute(
        text(
            """
            INSERT INTO codigos_alternativos (tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion)
            VALUES ('PERSONA', :pid, 'INTERNO_QR', :qr, 'Clave QR canónica de persona')
            """
        ),
        {"pid": row.id, "qr": clave_qr},
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="identidad",
        accion="CREAR_PERSONA",
        tipo_entidad="PERSONA",
        id_entidad=row.id,
        empresa_id=data.empresa_id,
        datos_despues={"curp": row.curp, "clave_interna_qr": row.clave_interna_qr},
    )
    await db.commit()
    return dict(row._mapping)


@router.get("/relaciones")
async def listar_relaciones(
    empresa_id: Optional[int] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("identidad.leer")),
    db: AsyncSession = Depends(get_db),
):
    where = "WHERE rl.empresa_id = :emp" if empresa_id is not None else ""
    params = {"emp": empresa_id} if empresa_id is not None else {}
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT
                    rl.id::text AS id, rl.persona_id::text AS persona_id,
                    p.curp, p.nombre || ' ' || p.apellido_paterno AS nombre_completo,
                    rl.empresa_id, e.clave AS empresa_clave,
                    rl.sucursal_id, rl.unidad_operativa_id,
                    rl.numero_empleado, rl.merqry_employee_id, rl.circuito_pago,
                    rl.puesto_nominal_id, pu.codigo_puesto AS puesto_nominal_codigo,
                    rl.fecha_ingreso, rl.estatus,
                    (
                        SELECT fot.funcion_operativa
                        FROM funciones_operativas_temporales fot
                        WHERE fot.relacion_laboral_id = rl.id AND fot.activa = TRUE
                        ORDER BY fot.creado_en DESC
                        LIMIT 1
                    ) AS funcion_temporal_activa
                FROM relaciones_laborales rl
                JOIN personas p ON p.id = rl.persona_id
                JOIN empresas e ON e.id = rl.empresa_id
                JOIN puestos pu ON pu.id = rl.puesto_nominal_id
                {where}
                ORDER BY rl.creado_en DESC
                """
            ),
            params,
        )
    ]
    return filter_rows_by_scope(rows, actor, "identidad.leer")


@router.post("/relaciones", status_code=status.HTTP_201_CREATED)
async def crear_relacion_laboral(
    data: CrearRelacionLaboralIn,
    actor: AuthenticatedActor = Depends(require_permission("identidad.escribir", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "identidad.escribir",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=2,
    )
    try:
        pid = str(uuid.UUID(data.persona_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Persona no encontrada.") from exc

    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO relaciones_laborales (
                        persona_id, empresa_id, sucursal_id, unidad_operativa_id,
                        numero_empleado, merqry_employee_id, circuito_pago,
                        puesto_nominal_id, fecha_ingreso, estatus
                    ) VALUES (
                        CAST(:pid AS uuid), :emp, :suc, :uo,
                        :num, :mrq, :circ, :puesto, :fing, 'ACTIVO'
                    )
                    RETURNING id::text AS id, persona_id::text AS persona_id, empresa_id,
                              sucursal_id, unidad_operativa_id, numero_empleado,
                              merqry_employee_id, circuito_pago, puesto_nominal_id, estatus
                    """
                ),
                {
                    "pid": pid,
                    "emp": data.empresa_id,
                    "suc": data.sucursal_id,
                    "uo": data.unidad_operativa_id,
                    "num": data.numero_empleado.strip().upper(),
                    "mrq": data.merqry_employee_id.strip() if data.merqry_employee_id else None,
                    "circ": data.circuito_pago,
                    "puesto": data.puesto_nominal_id,
                    "fing": data.fecha_ingreso,
                },
            )
        ).first()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Número de empleado duplicado en la empresa.") from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="identidad",
        accion="CREAR_RELACION_LABORAL",
        tipo_entidad="RELACION_LABORAL",
        id_entidad=row.id,
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return dict(row._mapping)


@router.post("/funciones-temporales", status_code=status.HTTP_201_CREATED)
async def asignar_funcion_temporal(
    data: AsignarFuncionTemporalIn,
    actor: AuthenticatedActor = Depends(require_permission("identidad.funcion_temporal", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """
    Asigna una funcion operativa temporal (ej. PESADOR, SUPERVISOR, TRASPLANTE)
    SIN modificar relaciones_laborales.puesto_nominal_id ni alterar RBAC.
    """
    try:
        rlid = str(uuid.UUID(data.relacion_laboral_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Relación laboral no encontrada.") from exc

    rel = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, puesto_nominal_id
                FROM relaciones_laborales
                WHERE id = CAST(:rlid AS uuid)
                """
            ),
            {"rlid": rlid},
        )
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relación laboral no encontrada.")

    target_uo = data.unidad_operativa_id or rel.unidad_operativa_id
    assert_scope(
        actor,
        "identidad.funcion_temporal",
        empresa_id=rel.empresa_id,
        sucursal_id=rel.sucursal_id,
        unidad_operativa_id=target_uo,
        min_level=2,
    )

    row = (
        await db.execute(
            text(
                """
                INSERT INTO funciones_operativas_temporales (
                    relacion_laboral_id, empresa_id, sucursal_id, unidad_operativa_id,
                    funcion_operativa, fecha_inicio, fecha_fin, motivo, autorizado_por_usuario_id
                ) VALUES (
                    CAST(:rlid AS uuid), :emp, :suc, :uo,
                    :func, :fini, :ffin, :mot, CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, relacion_laboral_id::text AS relacion_laboral_id,
                          empresa_id, unidad_operativa_id, funcion_operativa,
                          fecha_inicio, fecha_fin, motivo, activa
                """
            ),
            {
                "rlid": rlid,
                "emp": rel.empresa_id,
                "suc": rel.sucursal_id,
                "uo": target_uo,
                "func": data.funcion_operativa.strip().upper(),
                "fini": data.fecha_inicio,
                "ffin": data.fecha_fin,
                "mot": data.motivo.strip(),
                "uid": actor.usuario_id,
            },
        )
    ).first()

    await registrar_auditoria(
        db,
        actor,
        modulo="identidad",
        accion="ASIGNAR_FUNCION_TEMPORAL",
        tipo_entidad="FUNCION_TEMPORAL",
        id_entidad=row.id,
        empresa_id=rel.empresa_id,
        sucursal_id=rel.sucursal_id,
        unidad_operativa_id=target_uo,
        datos_despues={
            "relacion_laboral_id": rlid,
            "funcion_operativa": row.funcion_operativa,
            "puesto_nominal_intacto_id": rel.puesto_nominal_id,
        },
    )
    await db.commit()
    return {**dict(row._mapping), "puesto_nominal_intacto_id": rel.puesto_nominal_id}


@router.patch("/funciones-temporales/{func_id}/cerrar")
async def cerrar_funcion_temporal(
    func_id: str,
    actor: AuthenticatedActor = Depends(require_permission("identidad.funcion_temporal", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    try:
        fid = str(uuid.UUID(func_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Función temporal no encontrada.") from exc

    rec = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, activa
                FROM funciones_operativas_temporales
                WHERE id = CAST(:fid AS uuid)
                """
            ),
            {"fid": fid},
        )
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Función temporal no encontrada.")

    assert_scope(
        actor,
        "identidad.funcion_temporal",
        empresa_id=rec.empresa_id,
        sucursal_id=rec.sucursal_id,
        unidad_operativa_id=rec.unidad_operativa_id,
        min_level=2,
    )

    await db.execute(
        text(
            """
            UPDATE funciones_operativas_temporales
               SET activa = FALSE,
                   cerrada_en = NOW(),
                   fecha_fin = COALESCE(fecha_fin, CURRENT_DATE)
             WHERE id = CAST(:fid AS uuid)
            """
        ),
        {"fid": fid},
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="identidad",
        accion="CERRAR_FUNCION_TEMPORAL",
        tipo_entidad="FUNCION_TEMPORAL",
        id_entidad=fid,
        empresa_id=rec.empresa_id,
        sucursal_id=rec.sucursal_id,
        unidad_operativa_id=rec.unidad_operativa_id,
        datos_antes={"activa": rec.activa},
        datos_despues={"activa": False},
    )
    await db.commit()
    return {"id": fid, "activa": False}


@router.post("/etl/importar", status_code=status.HTTP_201_CREATED)
async def importar_etl_identidades(
    data: EtlImportIn,
    actor: AuthenticatedActor = Depends(require_permission("identidad.etl", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "identidad.etl",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=3,
    )
    resultado = await ejecutar_etl_identidades(
        db,
        fuente_nombre=data.fuente_nombre,
        empresa_id=data.empresa_id,
        registros=data.registros,
        actor=actor,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
    )
    await db.commit()
    return resultado


@router.get("/etl/cuarentena")
async def listar_cuarentena_etl(
    empresa_id: Optional[int] = Query(default=None),
    estatus: Optional[str] = Query(default="PENDIENTE_REVISION"),
    actor: AuthenticatedActor = Depends(require_permission("identidad.etl", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    clauses = []
    params: Dict[str, Any] = {}
    if empresa_id is not None:
        clauses.append("empresa_id = :emp")
        params["emp"] = empresa_id
    if estatus:
        clauses.append("estatus = :est")
        params["est"] = estatus
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT id::text AS id, lote_etl_id::text AS lote_etl_id, empresa_id,
                       fila_origen, motivo_conflicto,
                       persona_candidata_id::text AS persona_candidata_id,
                       payload_origen, estatus, creado_en
                FROM etl_cuarentena_identidad
                {where}
                ORDER BY creado_en DESC
                """
            ),
            params,
        )
    ]
    return filter_rows_by_scope(
        rows, actor, "identidad.etl", empresa_key="empresa_id", sucursal_key=None, unidad_key=None, min_level=3
    )
