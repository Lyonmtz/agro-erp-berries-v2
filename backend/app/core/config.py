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

    # Integracion Merqry (ERP central externo: estrictamente SOLO LECTURA)
    merqry_readonly_mode: bool = True
    merqry_mysql_host: Optional[str] = None
    merqry_mysql_port: int = 3307
    merqry_mysql_database: Optional[str] = None
    merqry_mysql_user: Optional[str] = None
    merqry_mysql_password: Optional[str] = None

    @field_validator("merqry_readonly_mode")
    @classmethod
    def enforce_merqry_readonly(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "Regla estricta violada: MERQRY_READONLY_MODE debe permanecer en True "
                "(nunca escribir ni ejecutar migraciones contra Merqry)."
            )
        return value

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
