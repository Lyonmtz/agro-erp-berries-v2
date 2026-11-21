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
RETURNS TRIGGER AS $$ DECLARE v_dias INT; BEGIN SELECT dias_intervalo_seguridad INTO v_dias FROM insumos_agricolas WHERE id = NEW.insumo_id; IF v_dias > 0 THEN UPDATE lotes_produccion SET estatus_fitosanitario = 'BLOQUEADO_INTERVALO_SEGURIDAD', fecha_liberacion_corte = GREATEST(COALESCE(fecha_liberacion_corte, NEW.fecha_aplicacion), NEW.fecha_aplicacion + (v_dias \vert{}\vert{} ' days')::INTERVAL) WHERE id = NEW.lote_id; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bloqueo_fitosanitario ON aplicaciones_fitosanitarias;
CREATE TRIGGER trg_bloqueo_fitosanitario
AFTER INSERT ON aplicaciones_fitosanitarias
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_lote_por_aplicacion();

CREATE OR REPLACE VIEW vw_direccion_rentabilidad_cultivo AS
SELECT 
    c.id AS cultivo_id, c.nombre AS cultivo,
    COALESCE(SUM(rc.cantidad_cajas), 0) AS cajas_cosechadas,
    COALESCE(SUM(rc.peso_kg_calculado), 0) AS kilos_totales,
    COALESCE((SELECT SUM(pd.total_percepcion_dia) FROM prenomina_diaria pd), 0) AS gasto_mano_obra_acumulado,
    COALESCE((SELECT SUM(af.costo_total_aplicacion) FROM aplicaciones_fitosanitarias af JOIN lotes_produccion lp ON af.lote_id = lp.id WHERE lp.cultivo_id = c.id), 0) AS gasto_insumos_cultivo
FROM cultivos c LEFT JOIN registros_cosecha rc ON c.id = rc.cultivo_id
GROUP BY c.id, c.nombre;
