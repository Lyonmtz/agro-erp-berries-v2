export interface UserScope {
  rol_codigo: string;
  nivel_acceso: number;
  empresa_id: number | null;
  sucursal_id: number | null;
  unidad_operativa_id: number | null;
  alcance_global: boolean;
}

export interface AuthUser {
  usuario_id: string;
  username: string;
  nombre_completo: string;
  email?: string;
  roles: UserScope[];
  permisos?: string[];
}

export interface AuthSession {
  access_token: string;
  token_type: string;
  usuario: AuthUser;
}

export interface HealthStatus {
  status: string;
  cultivos_activos: number;
  db_environment: string;
  merqry_mode: string;
  merqry_write_enabled: boolean;
}

export interface DailyEligibleWorker {
  person_id: string;
  relacion_laboral_id: string;
  numero_empleado: string;
  nombre_operativo: string;
  clave_interna_qr: string;
  empresa_id: number;
  sucursal_id: number;
  unidad_operativa_id: number;
  funcion_operativa_vigente: string;
  elegible_hoy: boolean;
  operaciones_autorizadas: string[];
}

export interface EligibilitySnapshot {
  id: "current";
  contract_version: string;
  fecha: string;
  generated_at: string;
  expires_at: string;
  ttl_hours: number;
  workers: DailyEligibleWorker[];
}

export interface LoteCatalogo {
  id: number;
  codigo_lote: string;
  nombre_sector: string;
  empresa_clave: string;
  variedad: string;
  superficie_ha: number;
  estatus_fitosanitario: string;
  cultivo: string;
  rancho: string;
}

export interface UnidadOperativa {
  id: number;
  empresa_id: number;
  sucursal_id: number;
  clave: string;
  nombre: string;
  tipo_unidad?: string;
}

export interface EmpresaItem {
  id: number;
  clave: string;
  razon_social: string;
  nombre_comercial: string;
}

export interface CachedCatalogs {
  id: "current";
  synced_at: string;
  lotes: LoteCatalogo[];
  empresas: EmpresaItem[];
  unidades: UnidadOperativa[];
}

export type OutboxStatus =
  | "QUEUED"
  | "SYNCING"
  | "COMMITTED"
  | "CONFLICT_409"
  | "ERROR_4XX"
  | "RETRY_WAIT";

export interface OutboxCommand {
  client_command_id: string;
  command_kind: "COSECHA_CAPTURA" | "CULTURAL_DIARIO" | "TRASPLANTE_CAMION" | "CIERRE_OPERATIVO";
  endpoint: string;
  method: "POST";
  label: string;
  payload: Record<string, unknown>;
  status: OutboxStatus;
  attempts: number;
  created_at: string;
  updated_at: string;
  server_ack?: Record<string, unknown> | null;
  last_error?: string | null;
}

export interface MerqryWriterStatus {
  merqry_write_enabled: boolean;
  merqry_write_mode: string;
  merqry_readonly_mirror_mode: boolean;
  allowed_modules_enabled: string[];
  allowed_target_schema: string | null;
  frozen_readonly_schemas: string[];
  allowed_circuit: string;
  company_mapping_by_clave: Record<string, [number, number]>;
  blacklisted_movs: string[];
  whitelisted_movs_by_module: Record<string, string[]>;
}
