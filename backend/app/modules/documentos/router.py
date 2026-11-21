from datetime import date
import json
from typing import Any, Dict, Optional
import uuid

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

router = APIRouter(prefix="/api/v1/documentos", tags=["Documentos y Códigos QR"])


class RegistrarDocumentoIn(BaseModel):
    tipo_entidad: str
    id_entidad: str = Field(..., min_length=1, max_length=64)
    tipo_documento_codigo: str
    empresa_id: int
    folio_documento: Optional[str] = None
    nombre_archivo: str = Field(..., min_length=1, max_length=200)
    ruta_storage: str = Field(..., min_length=1)
    sha256_archivo: Optional[str] = Field(default=None, max_length=64)
    fecha_emision: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    metadatos: Dict[str, Any] = Field(default_factory=dict)


class ValidarDocumentoIn(BaseModel):
    estatus: str = Field(..., pattern="^(VALIDADO|OBSERVADO|RECHAZADO)$")
    observaciones: Optional[str] = None


class RegistrarCodigoAlternativoIn(BaseModel):
    tipo_entidad: str
    id_entidad: str
    sistema_origen: str
    codigo_externo: str = Field(..., min_length=1, max_length=120)
    descripcion: Optional[str] = None
    empresa_id: int


@router.get("/tipos")
async def listar_tipos_documento(
    actor: AuthenticatedActor = Depends(require_permission("documentos.leer")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            text(
                """
                SELECT id, codigo, nombre, categoria, requiere_vigencia,
                       bloquea_operacion, prohibido_legal, activo
                FROM catalogo_tipos_documento
                WHERE activo = TRUE
                ORDER BY categoria, codigo
                """
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def registrar_documento(
    data: RegistrarDocumentoIn,
    actor: AuthenticatedActor = Depends(require_permission("documentos.escribir")),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(actor, "documentos.escribir", empresa_id=data.empresa_id)

    # Prohibicion explicita de guardar binarios/base64 en ruta_storage
    if data.ruta_storage.strip().lower().startswith("data:") or len(data.ruta_storage) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Prohibido guardar binarios/base64 en BD; use ruta_storage hacia almacenamiento documental.",
        )

    tipo = (
        await db.execute(
            text(
                """
                SELECT id, codigo, prohibido_legal
                FROM catalogo_tipos_documento
                WHERE codigo = :c AND activo = TRUE
                """
            ),
            {"c": data.tipo_documento_codigo.strip().upper()},
        )
    ).first()
    if not tipo:
        raise HTTPException(status_code=404, detail=f"Tipo documento {data.tipo_documento_codigo} no existe.")
    if tipo.prohibido_legal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"DOCUMENTO_PROHIBIDO_LEGALMENTE: '{tipo.codigo}' está prohibido por política legal.",
        )

    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO documentos_entidad (
                        tipo_entidad, id_entidad, tipo_documento_id, empresa_id,
                        folio_documento, nombre_archivo, ruta_storage, sha256_archivo,
                        estatus, fecha_emision, fecha_vencimiento, metadatos,
                        subido_por_usuario_id
                    ) VALUES (
                        :tent, :ient, :tid, :emp,
                        :folio, :nom, :ruta, :sha,
                        'CARGADO', :femi, :fvenc, CAST(:meta AS jsonb),
                        CAST(:uid AS uuid)
                    )
                    RETURNING id::text AS id, tipo_entidad, id_entidad, empresa_id,
                              folio_documento, nombre_archivo, ruta_storage, estatus, creado_en
                    """
                ),
                {
                    "tent": data.tipo_entidad.strip().upper(),
                    "ient": data.id_entidad.strip(),
                    "tid": tipo.id,
                    "emp": data.empresa_id,
                    "folio": data.folio_documento,
                    "nom": data.nombre_archivo.strip(),
                    "ruta": data.ruta_storage.strip(),
                    "sha": data.sha256_archivo,
                    "femi": data.fecha_emision,
                    "fvenc": data.fecha_vencimiento,
                    "meta": json.dumps(data.metadatos),
                    "uid": actor.usuario_id,
                },
            )
        ).first()
    except (IntegrityError, DBAPIError) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc.orig)) from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="documentos",
        accion="REGISTRAR_DOCUMENTO",
        tipo_entidad=data.tipo_entidad.upper(),
        id_entidad=data.id_entidad,
        empresa_id=data.empresa_id,
        datos_despues={"documento_id": row.id, "tipo": tipo.codigo, "archivo": row.nombre_archivo},
    )
    await db.commit()
    return dict(row._mapping)


@router.get("")
async def listar_documentos(
    tipo_entidad: Optional[str] = Query(default=None),
    id_entidad: Optional[str] = Query(default=None),
    empresa_id: Optional[int] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("documentos.leer")),
    db: AsyncSession = Depends(get_db),
):
    clauses = []
    params: Dict[str, Any] = {}
    if tipo_entidad:
        clauses.append("d.tipo_entidad = :tent")
        params["tent"] = tipo_entidad.upper()
    if id_entidad:
        clauses.append("d.id_entidad = :ient")
        params["ient"] = id_entidad
    if empresa_id is not None:
        clauses.append("d.empresa_id = :emp")
        params["emp"] = empresa_id
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT d.id::text AS id, d.tipo_entidad, d.id_entidad, d.empresa_id,
                       ct.codigo AS tipo_documento_codigo, ct.nombre AS tipo_documento_nombre,
                       d.folio_documento, d.nombre_archivo, d.ruta_storage, d.estatus,
                       d.fecha_emision, d.fecha_vencimiento, d.creado_en
                FROM documentos_entidad d
                JOIN catalogo_tipos_documento ct ON ct.id = d.tipo_documento_id
                {where}
                ORDER BY d.creado_en DESC
                """
            ),
            params,
        )
    ]
    return filter_rows_by_scope(
        rows, actor, "documentos.leer", empresa_key="empresa_id", sucursal_key=None, unidad_key=None
    )


@router.patch("/{doc_id}/validar")
async def validar_documento(
    doc_id: str,
    data: ValidarDocumentoIn,
    actor: AuthenticatedActor = Depends(require_permission("documentos.validar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    try:
        duid = str(uuid.UUID(doc_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.") from exc

    doc = (
        await db.execute(
            text(
                "SELECT id::text AS id, empresa_id, estatus, tipo_entidad, id_entidad FROM documentos_entidad WHERE id = CAST(:id AS uuid)"
            ),
            {"id": duid},
        )
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    assert_scope(actor, "documentos.validar", empresa_id=doc.empresa_id, min_level=2)

    await db.execute(
        text(
            """
            UPDATE documentos_entidad
               SET estatus = :est,
                   validado_por_usuario_id = CAST(:uid AS uuid),
                   validado_en = NOW(),
                   metadatos = metadatos || CAST(:obs AS jsonb)
             WHERE id = CAST(:id AS uuid)
            """
        ),
        {
            "est": data.estatus,
            "uid": actor.usuario_id,
            "obs": json.dumps({"observaciones_validacion": data.observaciones}),
            "id": duid,
        },
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="documentos",
        accion="VALIDAR_DOCUMENTO",
        tipo_entidad=doc.tipo_entidad,
        id_entidad=doc.id_entidad,
        empresa_id=doc.empresa_id,
        datos_antes={"estatus": doc.estatus},
        datos_despues={"estatus": data.estatus, "observaciones": data.observaciones},
    )
    await db.commit()
    return {"id": duid, "estatus": data.estatus}


@router.post("/codigos-alternativos", status_code=status.HTTP_201_CREATED)
async def registrar_codigo_alternativo(
    data: RegistrarCodigoAlternativoIn,
    actor: AuthenticatedActor = Depends(require_permission("documentos.escribir")),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(actor, "documentos.escribir", empresa_id=data.empresa_id)
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO codigos_alternativos (
                        tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion
                    ) VALUES (
                        :tent, :ient, :sis, :cod, :desc
                    )
                    RETURNING id, tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion
                    """
                ),
                {
                    "tent": data.tipo_entidad.strip().upper(),
                    "ient": data.id_entidad.strip(),
                    "sis": data.sistema_origen.strip().upper(),
                    "cod": data.codigo_externo.strip(),
                    "desc": data.descripcion,
                },
            )
        ).first()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="El código alternativo ya existe en ese sistema_origen para ese tipo_entidad.",
        ) from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="documentos",
        accion="REGISTRAR_CODIGO_ALTERNATIVO",
        tipo_entidad=row.tipo_entidad,
        id_entidad=row.id_entidad,
        empresa_id=data.empresa_id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return dict(row._mapping)


@router.get("/codigos-alternativos")
async def buscar_codigos_alternativos(
    tipo_entidad: Optional[str] = Query(default=None),
    id_entidad: Optional[str] = Query(default=None),
    sistema_origen: Optional[str] = Query(default=None),
    codigo_externo: Optional[str] = Query(default=None),
    actor: AuthenticatedActor = Depends(require_permission("documentos.leer")),
    db: AsyncSession = Depends(get_db),
):
    clauses = []
    params: Dict[str, Any] = {}
    if tipo_entidad:
        clauses.append("tipo_entidad = :tent")
        params["tent"] = tipo_entidad.upper()
    if id_entidad:
        clauses.append("id_entidad = :ient")
        params["ient"] = id_entidad
    if sistema_origen:
        clauses.append("sistema_origen = :sis")
        params["sis"] = sistema_origen.upper()
    if codigo_externo:
        clauses.append("codigo_externo = :cod")
        params["cod"] = codigo_externo
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion, activo
                FROM codigos_alternativos
                {where}
                ORDER BY id DESC
                """
            ),
            params,
        )
    ).all()
    return [dict(r._mapping) for r in rows]
