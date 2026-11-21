-- ============================================================================
-- 04_schema_tec_inv_log.sql
-- Area tecnica, insumos agricolas, bloqueo fitosanitario automatico (PHI)
-- y vista corregida de rentabilidad por cultivo sin duplicar prenomina.
-- ============================================================================

CREATE TABLE IF NOT EXISTS insumos_agricolas (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre_comercial VARCHAR(120) NOT NULL,
    ingrediente_activo VARCHAR(120) NOT NULL,
    categoria VARCHAR(30) CHECK (categoria IN ('FERTILIZANTE', 'AGROQUIMICO', 'BIOLOGICO', 'EMPAQUE', 'EPP', 'REFACCION')),
    unidad_medida VARCHAR(20) NOT NULL,
    dias_intervalo_seguridad INT DEFAULT 0 CHECK (dias_intervalo_seguridad >= 0),
    stock_actual NUMERIC(12,3) DEFAULT 0 CHECK (stock_actual >= 0),
    stock_minimo NUMERIC(12,3) DEFAULT 0,
    costo_promedio_unitario NUMERIC(10,2) DEFAULT 0,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS aplicaciones_fitosanitarias (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lote_id INT NOT NULL REFERENCES lotes_produccion(id),
    insumo_id INT NOT NULL REFERENCES insumos_agricolas(id),
    ingeniero_responsable_id UUID NOT NULL REFERENCES empleados(id),
    dosis_aplicada NUMERIC(10,3) NOT NULL,
    volumen_agua_litros NUMERIC(10,2),
    plaga_objetivo VARCHAR(100),
    fecha_aplicacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_liberacion_calculada TIMESTAMPTZ NOT NULL,
    costo_total_aplicacion NUMERIC(12,2) NOT NULL
);

CREATE OR REPLACE FUNCTION fn_bloquear_lote_por_aplicacion()
RETURNS TRIGGER AS $$
DECLARE
    v_dias INT;
BEGIN
    SELECT dias_intervalo_seguridad
      INTO v_dias
      FROM insumos_agricolas
     WHERE id = NEW.insumo_id;

    IF COALESCE(v_dias, 0) > 0 THEN
        UPDATE lotes_produccion
           SET estatus_fitosanitario = 'BLOQUEADO_INTERVALO_SEGURIDAD',
               fecha_liberacion_corte = GREATEST(
                   COALESCE(fecha_liberacion_corte, NEW.fecha_aplicacion),
                   NEW.fecha_aplicacion + (v_dias || ' days')::INTERVAL
               )
         WHERE id = NEW.lote_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bloqueo_fitosanitario ON aplicaciones_fitosanitarias;
CREATE TRIGGER trg_bloqueo_fitosanitario
AFTER INSERT ON aplicaciones_fitosanitarias
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_lote_por_aplicacion();

-- Vista corregida: prorratea la percepcion diaria (prenomina_diaria) entre los
-- cultivos realmente cosechados por cada trabajador en la fecha, evitando
-- duplicar el gasto total de mano de obra en todos los cultivos.
CREATE OR REPLACE VIEW vw_direccion_rentabilidad_cultivo AS
WITH cosecha_emp_dia_cultivo AS (
    SELECT
        j.fecha,
        rc.empleado_id,
        rc.cultivo_id,
        SUM(rc.cantidad_cajas) AS cajas_cultivo
    FROM registros_cosecha rc
    JOIN jornadas_diarias j ON j.id = rc.jornada_id
    GROUP BY j.fecha, rc.empleado_id, rc.cultivo_id
),
cosecha_emp_dia_total AS (
    SELECT
        fecha,
        empleado_id,
        SUM(cajas_cultivo) AS cajas_totales_dia
    FROM cosecha_emp_dia_cultivo
    GROUP BY fecha, empleado_id
),
mano_obra_por_cultivo AS (
    SELECT
        cdc.cultivo_id,
        ROUND(
            SUM(
                pd.total_percepcion_dia * (cdc.cajas_cultivo / NULLIF(cdt.cajas_totales_dia, 0))
            ),
            2
        ) AS gasto_mano_obra_acumulado
    FROM cosecha_emp_dia_cultivo cdc
    JOIN cosecha_emp_dia_total cdt
      ON cdt.fecha = cdc.fecha AND cdt.empleado_id = cdc.empleado_id
    JOIN prenomina_diaria pd
      ON pd.fecha = cdc.fecha AND pd.empleado_id = cdc.empleado_id
    GROUP BY cdc.cultivo_id
),
cosecha_por_cultivo AS (
    SELECT
        cultivo_id,
        SUM(cantidad_cajas) AS cajas_cosechadas,
        SUM(peso_kg_calculado) AS kilos_totales
    FROM registros_cosecha
    GROUP BY cultivo_id
),
insumos_por_cultivo AS (
    SELECT
        lp.cultivo_id,
        SUM(af.costo_total_aplicacion) AS gasto_insumos_cultivo
    FROM aplicaciones_fitosanitarias af
    JOIN lotes_produccion lp ON lp.id = af.lote_id
    GROUP BY lp.cultivo_id
)
SELECT
    c.id AS cultivo_id,
    c.codigo AS cultivo_codigo,
    c.nombre AS cultivo,
    c.empresa_clave,
    COALESCE(cc.cajas_cosechadas, 0) AS cajas_cosechadas,
    COALESCE(cc.kilos_totales, 0) AS kilos_totales,
    COALESCE(mo.gasto_mano_obra_acumulado, 0) AS gasto_mano_obra_acumulado,
    COALESCE(ic.gasto_insumos_cultivo, 0) AS gasto_insumos_cultivo
FROM cultivos c
LEFT JOIN cosecha_por_cultivo cc ON cc.cultivo_id = c.id
LEFT JOIN mano_obra_por_cultivo mo ON mo.cultivo_id = c.id
LEFT JOIN insumos_por_cultivo ic ON ic.cultivo_id = c.id
ORDER BY c.id;
