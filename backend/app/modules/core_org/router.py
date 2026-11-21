from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import (
    AuthenticatedActor,
    assert_scope,
    filter_rows_by_scope,
    require_permission,
)

router = APIRouter(prefix="/api/v1/org", tags=["Jerarquía Organizacional"])


class CrearSucursalIn(BaseModel):
    empresa_id: int
    clave: str = Field(..., min_length=2, max_length=30)
    nombre: str = Field(..., min_length=3, max_length=140)
    naturaleza_sucursal: str = "OPERATIVA"
    es_matriz: bool = False
    direccion: Optional[str] = None
    municipio: Optional[str] = None
    estado: Optional[str] = None
    codigo_postal: Optional[str] = None
    funciones: List[str] = Field(default_factory=list)


class CrearUnidadOperativaIn(BaseModel):
    empresa_id: int
    sucursal_id: int
    clave: str = Field(..., min_length=2, max_length=40)
    nombre: str = Field(..., min_length=3, max_length=140)
    tipo_unidad: str = "BLOQUE_MODULOS"
    rancho_id: Optional[int] = None


class CrearLocalizacionIn(BaseModel):
    empresa_id: int
    sucursal_id: int
    unidad_operativa_id: Optional[int] = None
    area_id: Optional[int] = None
    lote_id: Optional[int] = None
    clave: str = Field(..., min_length=2, max_length=60)
    nombre: str = Field(..., min_length=3, max_length=140)
    tipo_localizacion: str = "invernadero"
    capacidad_referencia: Optional[float] = None
    unidad_capacidad: Optional[str] = None


@router.get("/empresas")
async def listar_empresas(
    actor: AuthenticatedActor = Depends(require_permission("org.leer")),
    db: AsyncSession = Depends(get_db),
):
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text("SELECT id, clave, razon_social, nombre_comercial, tipo_persona, rfc, activa FROM empresas ORDER BY id")
        )
    ]
    allowed_ids = actor.allowed_empresas_for("org.leer")
    if allowed_ids is None:
        return rows
    return [r for r in rows if r["id"] in allowed_ids]


@router.get("/sucursales")
async def listar_sucursales(
    empresa_id: Optional[int] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("org.leer")),
    db: AsyncSession = Depends(get_db),
):
    where = "WHERE s.empresa_id = :emp" if empresa_id is not None else ""
    params = {"emp": empresa_id} if empresa_id is not None else {}
    sql = f"""
        SELECT
            s.id, s.empresa_id, e.clave AS empresa_clave, s.clave, s.nombre,
            s.naturaleza_sucursal, s.es_matriz, s.municipio, s.estado, s.activa,
            COALESCE(
                ARRAY_AGG(sf.funcion ORDER BY sf.funcion) FILTER (WHERE sf.funcion IS NOT NULL AND sf.activa = TRUE),
                ARRAY[]::text[]
            ) AS funciones
        FROM sucursales s
        JOIN empresas e ON e.id = s.empresa_id
        LEFT JOIN sucursal_funciones sf ON sf.sucursal_id = s.id
        {where}
        GROUP BY s.id, e.clave
        ORDER BY s.empresa_id, s.es_matriz DESC, s.id
    """
    rows = [dict(r._mapping) for r in await db.execute(text(sql), params)]
    return filter_rows_by_scope(
        rows,
        actor,
        "org.leer",
        empresa_key="empresa_id",
        sucursal_key="id",
        unidad_key=None,
    )


@router.post("/sucursales", status_code=status.HTTP_201_CREATED)
async def crear_sucursal(
    data: CrearSucursalIn,
    actor: AuthenticatedActor = Depends(require_permission("org.escribir", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    # Crear una sucursal es escritura a nivel empresa (un rol acotado a una sucursal/unidad NO pasa)
    assert_scope(actor, "org.escribir", empresa_id=data.empresa_id, min_level=3)

    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO sucursales (
                        empresa_id, clave, nombre, naturaleza_sucursal, es_matriz,
                        direccion, municipio, estado, codigo_postal
                    ) VALUES (
                        :emp, :clave, :nom, :nat, :mat, :dir, :mun, :edo, :cp
                    )
                    RETURNING id, empresa_id, clave, nombre, naturaleza_sucursal, es_matriz, activa
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "clave": data.clave.strip().upper(),
                    "nom": data.nombre.strip(),
                    "nat": data.naturaleza_sucursal.strip().upper(),
                    "mat": data.es_matriz,
                    "dir": data.direccion,
                    "mun": data.municipio,
                    "edo": data.estado,
                    "cp": data.codigo_postal,
                },
            )
        ).first()

        for fn in data.funciones:
            await db.execute(
                text(
                    """
                    INSERT INTO sucursal_funciones (sucursal_id, funcion, activa)
                    VALUES (:sid, :fn, TRUE)
                    ON CONFLICT (sucursal_id, funcion) DO NOTHING
                    """
                ),
                {"sid": row.id, "fn": fn.strip().lower()},
            )
    except IntegrityError as exc:
        await db.rollback()
        msg = str(exc.orig)
        if "ux_sucursales_una_matriz_por_empresa" in msg:
            raise HTTPException(
                status_code=409,
                detail="La empresa ya cuenta con una sucursal MATRIZ activa (regla única matriz).",
            ) from exc
        raise HTTPException(status_code=409, detail=f"Conflicto de integridad en sucursal: {msg}") from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="core_org",
        accion="CREAR_SUCURSAL",
        tipo_entidad="SUCURSAL",
        id_entidad=str(row.id),
        empresa_id=data.empresa_id,
        sucursal_id=row.id,
        datos_despues={"clave": row.clave, "es_matriz": row.es_matriz, "funciones": data.funciones},
    )
    await db.commit()
    return {**dict(row._mapping), "funciones": data.funciones}


@router.get("/unidades")
async def listar_unidades(
    empresa_id: Optional[int] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("org.leer")),
    db: AsyncSession = Depends(get_db),
):
    where = "WHERE uo.empresa_id = :emp" if empresa_id is not None else ""
    params = {"emp": empresa_id} if empresa_id is not None else {}
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT uo.id, uo.empresa_id, e.clave AS empresa_clave,
                       uo.sucursal_id, s.clave AS sucursal_clave,
                       uo.clave, uo.nombre, uo.tipo_unidad, uo.rancho_id, uo.activa
                FROM unidades_operativas uo
                JOIN empresas e ON e.id = uo.empresa_id
                JOIN sucursales s ON s.id = uo.sucursal_id
                {where}
                ORDER BY uo.empresa_id, uo.id
                """
            ),
            params,
        )
    ]
    return filter_rows_by_scope(
        rows,
        actor,
        "org.leer",
        empresa_key="empresa_id",
        sucursal_key="sucursal_id",
        unidad_key="id",
    )


@router.post("/unidades", status_code=status.HTTP_201_CREATED)
async def crear_unidad_operativa(
    data: CrearUnidadOperativaIn,
    actor: AuthenticatedActor = Depends(require_permission("org.escribir", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "org.escribir",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        min_level=3,
    )
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO unidades_operativas (
                        empresa_id, sucursal_id, clave, nombre, tipo_unidad, rancho_id
                    ) VALUES (
                        :emp, :suc, :clave, :nom, :tipo, :rid
                    )
                    RETURNING id, empresa_id, sucursal_id, clave, nombre, tipo_unidad, rancho_id, activa
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "suc": data.sucursal_id,
                    "clave": data.clave.strip().upper(),
                    "nom": data.nombre.strip(),
                    "tipo": data.tipo_unidad.strip().upper(),
                    "rid": data.rancho_id,
                },
            )
        ).first()
    except (IntegrityError, DBAPIError) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc.orig)) from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="core_org",
        accion="CREAR_UNIDAD_OPERATIVA",
        tipo_entidad="UNIDAD_OPERATIVA",
        id_entidad=str(row.id),
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=row.id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return dict(row._mapping)


@router.get("/localizaciones")
async def listar_localizaciones(
    empresa_id: Optional[int] = Query(default=None),
    unidad_operativa_id: Optional[int] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("org.leer")),
    db: AsyncSession = Depends(get_db),
):
    clauses = []
    params = {}
    if empresa_id is not None:
        clauses.append("lf.empresa_id = :emp")
        params["emp"] = empresa_id
    if unidad_operativa_id is not None:
        clauses.append("lf.unidad_operativa_id = :uo")
        params["uo"] = unidad_operativa_id
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT lf.id, lf.empresa_id, e.clave AS empresa_clave,
                       lf.sucursal_id, lf.unidad_operativa_id, lf.area_id, lf.lote_id,
                       lf.clave, lf.nombre, lf.tipo_localizacion, lf.activa
                FROM localizaciones_fisicas lf
                JOIN empresas e ON e.id = lf.empresa_id
                {where}
                ORDER BY lf.empresa_id, lf.id
                """
            ),
            params,
        )
    ]
    return filter_rows_by_scope(rows, actor, "org.leer")


@router.post("/localizaciones", status_code=status.HTTP_201_CREATED)
async def crear_localizacion(
    data: CrearLocalizacionIn,
    actor: AuthenticatedActor = Depends(require_permission("org.escribir", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "org.escribir",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=2,
    )
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO localizaciones_fisicas (
                        empresa_id, sucursal_id, unidad_operativa_id, area_id, lote_id,
                        clave, nombre, tipo_localizacion, capacidad_referencia, unidad_capacidad
                    ) VALUES (
                        :emp, :suc, :uo, :area, :lote, :clave, :nom, :tipo, :cap, :ucap
                    )
                    RETURNING id, empresa_id, sucursal_id, unidad_operativa_id, area_id,
                              lote_id, clave, nombre, tipo_localizacion, activa
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "suc": data.sucursal_id,
                    "uo": data.unidad_operativa_id,
                    "area": data.area_id,
                    "lote": data.lote_id,
                    "clave": data.clave.strip().upper(),
                    "nom": data.nombre.strip(),
                    "tipo": data.tipo_localizacion.strip().lower(),
                    "cap": data.capacidad_referencia,
                    "ucap": data.unidad_capacidad,
                },
            )
        ).first()
    except (IntegrityError, DBAPIError) as exc:
        await db.rollback()
        msg = str(exc.orig)
        if "INCONSISTENCIA_CONTEXTO" in msg:
            raise HTTPException(status_code=422, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="core_org",
        accion="CREAR_LOCALIZACION",
        tipo_entidad="LOCALIZACION",
        id_entidad=str(row.id),
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return dict(row._mapping)
