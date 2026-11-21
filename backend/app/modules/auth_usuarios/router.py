from datetime import datetime, timedelta, timezone
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import (
    AuthenticatedActor,
    assert_scope,
    create_access_token,
    get_current_user,
    hash_secret,
    load_actor_from_db,
    require_permission,
    verify_secret,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth & RBAC"])


class LoginIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=60)
    password: str = Field(..., min_length=4, max_length=128)


class CrearUsuarioIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=60)
    email: Optional[str] = None
    nombre_completo: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)
    persona_id: Optional[str] = None


class AsignarRolIn(BaseModel):
    rol_codigo: str
    empresa_id: Optional[int] = None
    sucursal_id: Optional[int] = None
    unidad_operativa_id: Optional[int] = None
    alcance_global: bool = False


class EstablecerNipIn(BaseModel):
    persona_id: str
    nip: str = Field(..., pattern=r"^\d{4,6}$")


class VerificarNipIn(BaseModel):
    persona_id: str
    nip: str = Field(..., pattern=r"^\d{4,6}$")


def _serialize_actor(actor: AuthenticatedActor) -> dict:
    return {
        "usuario_id": actor.usuario_id,
        "username": actor.username,
        "nombre_completo": actor.nombre_completo,
        "email": actor.email,
        "persona_id": actor.persona_id,
        "alcance_global": actor.is_global,
        "nivel_autorizacion_max": actor.max_nivel_autorizacion,
        "roles": [
            {
                "rol_codigo": g.rol_codigo,
                "nivel_autorizacion": g.nivel_autorizacion,
                "empresa_id": g.empresa_id,
                "sucursal_id": g.sucursal_id,
                "unidad_operativa_id": g.unidad_operativa_id,
                "alcance_global": g.alcance_global,
                "permisos": sorted(g.permisos),
            }
            for g in actor.grants
        ],
    }


@router.post("/login")
async def login(data: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, username, password_hash, activo
                FROM usuarios
                WHERE LOWER(username) = LOWER(:u)
                """
            ),
            {"u": data.username.strip()},
        )
    ).first()

    if not row or not row.activo or not verify_secret(data.password, row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    await db.execute(
        text("UPDATE usuarios SET ultimo_login_en = NOW() WHERE id = CAST(:uid AS uuid)"),
        {"uid": row.id},
    )
    ip = request.client.host if request.client else None
    actor = await load_actor_from_db(db, row.id, ip_origen=ip)
    await registrar_auditoria(
        db,
        actor,
        modulo="auth_usuarios",
        accion="LOGIN_OK",
        tipo_entidad="USUARIO",
        id_entidad=actor.usuario_id,
    )
    await db.commit()

    token = create_access_token(actor.usuario_id, actor.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": _serialize_actor(actor),
    }


@router.get("/me")
async def me(actor: AuthenticatedActor = Depends(get_current_user)):
    return _serialize_actor(actor)


@router.get("/roles")
async def listar_roles(
    actor: AuthenticatedActor = Depends(require_permission("auth.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            text(
                """
                SELECT r.id, r.codigo, r.nombre, r.nivel_autorizacion, r.descripcion,
                       COALESCE(ARRAY_AGG(p.codigo ORDER BY p.codigo) FILTER (WHERE p.codigo IS NOT NULL), ARRAY[]::text[]) AS permisos
                FROM roles r
                LEFT JOIN roles_permisos rp ON rp.rol_id = r.id
                LEFT JOIN permisos p ON p.id = rp.permiso_id
                WHERE r.activo = TRUE
                GROUP BY r.id
                ORDER BY r.nivel_autorizacion DESC, r.codigo
                """
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
async def crear_usuario(
    data: CrearUsuarioIn,
    actor: AuthenticatedActor = Depends(require_permission("auth.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    if not actor.is_global:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador con alcance global puede crear usuarios.",
        )

    persona_uuid = None
    if data.persona_id:
        try:
            persona_uuid = str(uuid.UUID(data.persona_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="persona_id inválido.") from exc

    pwd_hash = hash_secret(data.password)
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO usuarios (username, email, nombre_completo, password_hash, persona_id)
                    VALUES (:u, :em, :nom, :ph, CAST(:pid AS uuid))
                    RETURNING id::text AS id, username, email, nombre_completo, activo
                    """
                ),
                {
                    "u": data.username.strip().lower(),
                    "em": data.email.strip().lower() if data.email else None,
                    "nom": data.nombre_completo.strip(),
                    "ph": pwd_hash,
                    "pid": persona_uuid,
                },
            )
        ).first()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Username o email ya registrado.") from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="auth_usuarios",
        accion="CREAR_USUARIO",
        tipo_entidad="USUARIO",
        id_entidad=row.id,
        datos_despues={"username": row.username, "nombre_completo": row.nombre_completo},
    )
    await db.commit()
    return dict(row._mapping)


@router.post("/usuarios/{usuario_id}/roles", status_code=status.HTTP_201_CREATED)
async def asignar_rol_usuario(
    usuario_id: str,
    data: AsignarRolIn,
    actor: AuthenticatedActor = Depends(require_permission("auth.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = str(uuid.UUID(usuario_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.") from exc

    if data.alcance_global and not actor.is_global:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un actor con alcance global puede otorgar alcance_global.",
        )
    if not data.alcance_global:
        if data.empresa_id is None:
            raise HTTPException(
                status_code=400,
                detail="Debe indicar empresa_id cuando alcance_global=False.",
            )
        assert_scope(
            actor,
            "auth.gestionar",
            empresa_id=data.empresa_id,
            sucursal_id=data.sucursal_id,
            unidad_operativa_id=data.unidad_operativa_id,
            min_level=3,
        )

    rol = (
        await db.execute(
            text("SELECT id, codigo, nivel_autorizacion FROM roles WHERE codigo = :c AND activo = TRUE"),
            {"c": data.rol_codigo.strip().upper()},
        )
    ).first()
    if not rol:
        raise HTTPException(status_code=404, detail=f"Rol {data.rol_codigo} no encontrado.")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO usuarios_roles (
                    usuario_id, rol_id, empresa_id, sucursal_id, unidad_operativa_id, alcance_global
                ) VALUES (
                    CAST(:uid AS uuid), :rid, :emp, :suc, :uo, :glob
                )
                RETURNING id, usuario_id::text AS usuario_id, rol_id, empresa_id, sucursal_id,
                          unidad_operativa_id, alcance_global
                """
            ),
            {
                "uid": uid,
                "rid": rol.id,
                "emp": data.empresa_id,
                "suc": data.sucursal_id,
                "uo": data.unidad_operativa_id,
                "glob": data.alcance_global,
            },
        )
    ).first()

    await registrar_auditoria(
        db,
        actor,
        modulo="auth_usuarios",
        accion="ASIGNAR_ROL",
        tipo_entidad="USUARIO_ROL",
        id_entidad=str(row.id),
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        datos_despues={
            "usuario_id": uid,
            "rol_codigo": rol.codigo,
            "alcance_global": data.alcance_global,
        },
    )
    await db.commit()
    return dict(row._mapping)


@router.post("/nips/establecer")
async def establecer_nip(
    data: EstablecerNipIn,
    actor: AuthenticatedActor = Depends(require_permission("auth.nip.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = str(uuid.UUID(data.persona_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Persona no encontrada.") from exc

    rel = (
        await db.execute(
            text(
                """
                SELECT empresa_id, sucursal_id, unidad_operativa_id
                FROM relaciones_laborales
                WHERE persona_id = CAST(:pid AS uuid)
                ORDER BY creado_en DESC
                LIMIT 1
                """
            ),
            {"pid": pid},
        )
    ).first()
    if rel:
        assert_scope(
            actor,
            "auth.nip.gestionar",
            empresa_id=rel.empresa_id,
            sucursal_id=rel.sucursal_id,
            unidad_operativa_id=rel.unidad_operativa_id,
            min_level=2,
        )

    nip_hash = hash_secret(data.nip)
    await db.execute(
        text(
            """
            INSERT INTO nips_personal (persona_id, nip_hash, intentos_fallidos, bloqueado_hasta, actualizado_en)
            VALUES (CAST(:pid AS uuid), :nh, 0, NULL, NOW())
            ON CONFLICT (persona_id) DO UPDATE SET
                nip_hash = EXCLUDED.nip_hash,
                intentos_fallidos = 0,
                bloqueado_hasta = NULL,
                actualizado_en = NOW()
            """
        ),
        {"pid": pid, "nh": nip_hash},
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="auth_usuarios",
        accion="ESTABLECER_NIP",
        tipo_entidad="PERSONA",
        id_entidad=pid,
        empresa_id=rel.empresa_id if rel else None,
        datos_despues={"nip_hasheado": True},
    )
    await db.commit()
    return {"status": "OK", "persona_id": pid, "nip_configurado": True}


@router.post("/nips/verificar")
async def verificar_nip(
    data: VerificarNipIn,
    actor: AuthenticatedActor = Depends(require_permission("auth.nip.verificar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = str(uuid.UUID(data.persona_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Persona no encontrada.") from exc

    rec = (
        await db.execute(
            text(
                """
                SELECT nip_hash, intentos_fallidos, bloqueado_hasta
                FROM nips_personal
                WHERE persona_id = CAST(:pid AS uuid)
                """
            ),
            {"pid": pid},
        )
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="La persona no tiene NIP configurado.")

    now = datetime.now(timezone.utc)
    if rec.bloqueado_hasta and rec.bloqueado_hasta > now:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="NIP bloqueado temporalmente por intentos fallidos.",
        )

    if not verify_secret(data.nip, rec.nip_hash):
        intentos = int(rec.intentos_fallidos) + 1
        bloqueo = now + timedelta(minutes=15) if intentos >= 5 else None
        await db.execute(
            text(
                """
                UPDATE nips_personal
                   SET intentos_fallidos = :i,
                       bloqueado_hasta = :b,
                       actualizado_en = NOW()
                 WHERE persona_id = CAST(:pid AS uuid)
                """
            ),
            {"i": intentos, "b": bloqueo, "pid": pid},
        )
        await db.commit()
        return {"valido": False, "intentos_fallidos": intentos, "bloqueado": bloqueo is not None}

    await db.execute(
        text(
            """
            UPDATE nips_personal
               SET intentos_fallidos = 0, bloqueado_hasta = NULL, actualizado_en = NOW()
             WHERE persona_id = CAST(:pid AS uuid)
            """
        ),
        {"pid": pid},
    )
    await db.commit()
    return {"valido": True, "persona_id": pid}
