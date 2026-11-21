-- ============================================================================
-- 99_mark_disposable_test.sql
-- SOLO montado en el contenedor efimero db_test (tmpfs) para marcar
-- explicitamente app_db_metadata.db_environment = 'DISPOSABLE_TEST'.
-- NUNCA montar este script en la base operativa agro_berries_erp.
-- ============================================================================

UPDATE app_db_metadata
   SET db_environment = 'DISPOSABLE_TEST',
       notes = 'Base efimera desechable verificada exclusivamente para suite automatizada pytest.',
       updated_at = NOW()
 WHERE id = 1;
