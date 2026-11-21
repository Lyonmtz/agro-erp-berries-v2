from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Set

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

bearer_scheme = HTTPBearer(auto_error=False)


def hash_secret(plain: str) -> str:
    """Hashea passwords y NIPs usando bcrypt (nunca texto plano)."""
    raw = plain.encode("utf-8")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_secret(plain: str, hashed: str) -> bool:
    """Verifica password o NIP contra hash bcrypt (compatible con pgcrypto bf)."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    user_id: str,
    username: str,
    expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@dataclass(frozen=True)
class RoleGrant:
    rol_codigo: str
    nivel_autorizacion: int
    empresa_id: Optional[int]
    sucursal_id: Optional[int]
    unidad_operativa_id: Optional[int]
    alcance_global: bool
    permisos: frozenset[str] = field(default_factory=frozenset)


@dataclass
class AuthenticatedActor:
    usuario_id: str
    username: str
    nombre_completo: str
    email: Optional[str]
    persona_id: Optional[str]
    grants: List[RoleGrant]
    ip_origen: Optional[str] = None

    @property
    def is_global(self) -> bool:
        return any(g.alcance_global for g in self.grants)

    @property
    def max_nivel_autorizacion(self) -> int:
        return max((g.nivel_autorizacion for g in self.grants), default=0)

    @property
    def primary_rol(self) -> Optional[str]:
        if not self.grants:
            return None
        top = max(self.grants, key=lambda g: g.nivel_autorizacion)
        return top.rol_codigo

    def all_permissions(self) -> Set[str]:
        out: Set[str] = set()
        for g in self.grants:
            out.update(g.permisos)
        return out

    def has_any_permission(self, permiso: str, min_level: int = 1) -> bool:
        return any(
            permiso in g.permisos and g.nivel_autorizacion >= min_level
            for g in self.grants
        )

    def has_scoped_permission(
        self,
        permiso: str,
        empresa_id: Optional[int] = None,
        sucursal_id: Optional[int] = None,
        unidad_operativa_id: Optional[int] = None,
        min_level: int = 1,
    ) -> bool:
        """
        Evaluacion server-side estricta de RBAC + alcance:
        - Un permiso acotado a sucursal o unidad NUNCA autoriza escrituras a nivel empresa
          ni sobre otra empresa/sucursal/unidad.
        """
        for g in self.grants:
            if permiso not in g.permisos or g.nivel_autorizacion < min_level:
                continue
            if g.alcance_global:
                return True
            if empresa_id is None:
                # Si la operacion requiere empresa explicita y el grant no es global,
                # un grant acotado a unidad/sucursal no puede actuar sin contexto.
                continue
            if g.empresa_id != empresa_id:
                continue
            if g.sucursal_id is not None:
                if sucursal_id is None or g.sucursal_id != sucursal_id:
                    continue
            if g.unidad_operativa_id is not None:
                if unidad_operativa_id is None or g.unidad_operativa_id != unidad_operativa_id:
                    continue
            return True
        return False

    def allowed_empresas_for(self, permiso: str, min_level: int = 1) -> Optional[Set[int]]:
        """
        Devuelve None si el actor tiene alcance global para ese permiso,
        o el conjunto de empresa_ids permitidos (posiblemente vacio).
        """
        allowed: Set[int] = set()
        for g in self.grants:
            if permiso not in g.permisos or g.nivel_autorizacion < min_level:
                continue
            if g.alcance_global:
                return None
            if g.empresa_id is not None:
                allowed.add(g.empresa_id)
        return allowed

    def allowed_unidades_for(
        self, permiso: str, empresa_id: int, min_level: int = 1
    ) -> Optional[Set[int]]:
        """
        Para consultas filtradas dentro de una empresa:
        - None => acceso a todas las unidades de esa empresa
        - Set[int] => solo esas unidades_operativas
        """
        units: Set[int] = set()
        for g in self.grants:
            if permiso not in g.permisos or g.nivel_autorizacion < min_level:
                continue
            if g.alcance_global:
                return None
            if g.empresa_id != empresa_id:
                continue
            if g.unidad_operativa_id is None:
                return None
            units.add(g.unidad_operativa_id)
        return units


async def load_actor_from_db(
    db: AsyncSession, user_id: str, ip_origen: Optional[str] = None
) -> AuthenticatedActor:
    user_row = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, username, email, nombre_completo,
                       persona_id::text AS persona_id, activo
                FROM usuarios
                WHERE id = CAST(:uid AS uuid)
                """
            ),
            {"uid": user_id},
        )
    ).first()

    if not user_row or not user_row.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o inexistente.",
        )

    role_rows = (
        await db.execute(
            text(
                """
                SELECT
                    ur.id AS grant_id,
                    r.codigo AS rol_codigo,
                    r.nivel_autorizacion,
                    ur.empresa_id,
                    ur.sucursal_id,
                    ur.unidad_operativa_id,
                    ur.alcance_global,
                    COALESCE(
                        ARRAY_AGG(DISTINCT p.codigo) FILTER (WHERE p.codigo IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS permisos
                FROM usuarios_roles ur
                JOIN roles r ON r.id = ur.rol_id AND r.activo = TRUE
                LEFT JOIN roles_permisos rp ON rp.rol_id = r.id
                LEFT JOIN permisos p ON p.id = rp.permiso_id
                WHERE ur.usuario_id = CAST(:uid AS uuid)
                  AND ur.activo = TRUE
                GROUP BY ur.id, r.codigo, r.nivel_autorizacion,
                         ur.empresa_id, ur.sucursal_id, ur.unidad_operativa_id, ur.alcance_global
                """
            ),
            {"uid": user_id},
        )
    ).all()

    grants = [
        RoleGrant(
            rol_codigo=row.rol_codigo,
            nivel_autorizacion=int(row.nivel_autorizacion),
            empresa_id=row.empresa_id,
            sucursal_id=row.sucursal_id,
            unidad_operativa_id=row.unidad_operativa_id,
            alcance_global=bool(row.alcance_global),
            permisos=frozenset(row.permisos or []),
        )
        for row in role_rows
    ]

    return AuthenticatedActor(
        usuario_id=user_row.id,
        username=user_row.username,
        nombre_completo=user_row.nombre_completo,
        email=user_row.email,
        persona_id=user_row.persona_id,
        grants=grants,
        ip_origen=ip_origen,
    )


async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedActor:
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida (Bearer JWT).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(creds.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin sujeto válido.",
        )
    ip = request.client.host if request.client else None
    return await load_actor_from_db(db, user_id, ip_origen=ip)


def require_permission(permiso: str, min_level: int = 1):
    async def _dep(actor: AuthenticatedActor = Depends(get_current_user)) -> AuthenticatedActor:
        if not actor.has_any_permission(permiso, min_level=min_level):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso insuficiente: se requiere '{permiso}' (nivel >= {min_level}).",
            )
        return actor

    return _dep


def assert_scope(
    actor: AuthenticatedActor,
    permiso: str,
    *,
    empresa_id: Optional[int] = None,
    sucursal_id: Optional[int] = None,
    unidad_operativa_id: Optional[int] = None,
    min_level: int = 1,
) -> None:
    if not actor.has_scoped_permission(
        permiso,
        empresa_id=empresa_id,
        sucursal_id=sucursal_id,
        unidad_operativa_id=unidad_operativa_id,
        min_level=min_level,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Fuera de alcance autorizado para '{permiso}' "
                f"(empresa={empresa_id}, sucursal={sucursal_id}, unidad={unidad_operativa_id})."
            ),
        )


def filter_rows_by_scope(
    rows: Iterable[dict],
    actor: AuthenticatedActor,
    permiso: str,
    *,
    empresa_key: str = "empresa_id",
    sucursal_key: Optional[str] = "sucursal_id",
    unidad_key: Optional[str] = "unidad_operativa_id",
    min_level: int = 1,
) -> List[dict]:
    """Filtra listas de registros respetando el alcance exacto de cada grant del actor."""
    result: List[dict] = []
    for row in rows:
        emp = row.get(empresa_key)
        suc = row.get(sucursal_key) if sucursal_key else None
        uo = row.get(unidad_key) if unidad_key else None
        # Para lecturas: un grant acotado a una unidad puede leer su propia empresa/sucursal
        # si la fila no tiene nivel inferior, pero si la fila tiene sucursal/unidad se valida exacto.
        allowed = False
        for g in actor.grants:
            if permiso not in g.permisos or g.nivel_autorizacion < min_level:
                continue
            if g.alcance_global:
                allowed = True
                break
            if emp is not None and g.empresa_id != emp:
                continue
            if suc is not None and g.sucursal_id is not None and g.sucursal_id != suc:
                continue
            if uo is not None and g.unidad_operativa_id is not None and g.unidad_operativa_id != uo:
                continue
            allowed = True
            break
        if allowed:
            result.append(row)
    return result
