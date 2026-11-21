from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion central de AGRO-ERP Berries v2."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AGRO-ERP Berries"
    app_version: str = "2.0.0"
    environment: str = "DEVELOPMENT"
    tz: str = "America/Mexico_City"

    # PostgreSQL operativo
    database_url: str = (
        "postgresql+asyncpg://agro_admin:DevPassword2026!@db:5432/agro_berries_erp"
    )

    # PostgreSQL de pruebas desechable verificada
    test_database_url: Optional[str] = None
    allow_destructive_test_db: bool = False

    # Seguridad
    secret_key: str = "DevSecretKey_Berries_2026"
    cors_origins: str = "*"

    # Integracion Merqry (ERP central externo: estrictamente SOLO LECTURA por defecto)
    merqry_readonly_mode: bool = True
    merqry_mysql_host: Optional[str] = None
    merqry_mysql_port: int = 3307
    merqry_mysql_database: Optional[str] = None
    merqry_mysql_user: Optional[str] = None
    merqry_mysql_password: Optional[str] = None

    # Modulo futuro merqry_writer: APAGADO POR DEFECTO (fail-closed)
    merqry_write_enabled: bool = False
    merqry_write_mode: str = "DISABLED"  # DISABLED | STAGING_DRAFT_ONLY | CONTROLLED_APPLY
    merqry_write_allowed_modules: str = ""  # Ej. "AP,INCID" (vacio por defecto)
    merqry_write_allowed_schema: str = ""  # Debe coincidir con SELECT DATABASE() en clon/lab
    merqry_write_allowed_host: str = ""
    merqry_write_mysql_host: Optional[str] = None
    merqry_write_mysql_port: int = 3308
    merqry_write_mysql_user: Optional[str] = None
    merqry_write_mysql_password: Optional[str] = None
    merqry_write_actor_user: str = "AGRO_BOT"

    @field_validator("merqry_readonly_mode")
    @classmethod
    def enforce_merqry_readonly(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "Regla estricta violada: MERQRY_READONLY_MODE debe permanecer en True "
                "(nunca escribir ni ejecutar migraciones contra el espejo de solo lectura Merqry)."
            )
        return value

    @field_validator("merqry_write_mode")
    @classmethod
    def validate_merqry_write_mode(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DISABLED", "STAGING_DRAFT_ONLY", "CONTROLLED_APPLY"}:
            raise ValueError(
                "MERQRY_WRITE_MODE invalido; valores permitidos: "
                "DISABLED, STAGING_DRAFT_ONLY, CONTROLLED_APPLY."
            )
        return normalized

    @field_validator("merqry_write_allowed_schema")
    @classmethod
    def forbid_frozen_backup_schema(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower() == "mq_bio_organicos_analisis":
            raise ValueError(
                "PROHIBIDO: 'mq_bio_organicos_analisis' es respaldo forense de SOLO LECTURA "
                "y nunca puede configurarse como destino de merqry_writer."
            )
        return cleaned

    @property
    def merqry_write_allowed_modules_set(self) -> set[str]:
        return {
            m.strip().upper()
            for m in self.merqry_write_allowed_modules.split(",")
            if m.strip()
        }

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
