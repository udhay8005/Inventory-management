-- Reset all WMS SKU + EAN-13 Postgres sequences to 1.
-- Re-run after a demo wipe / before importing fresh data.
DO $$
DECLARE s record;
BEGIN
    FOR s IN SELECT id FROM ir_sequence WHERE code LIKE 'wms.sku.%' OR code='wms.barcode.ean13'
    LOOP
        IF EXISTS (SELECT 1 FROM pg_class WHERE relkind='S' AND relname=format('ir_sequence_%s',lpad(s.id::text,3,'0'))) THEN
            EXECUTE format('ALTER SEQUENCE ir_sequence_%s RESTART WITH 1',lpad(s.id::text,3,'0'));
        END IF;
    END LOOP;
END $$;
SELECT 'Reset OK' AS status;