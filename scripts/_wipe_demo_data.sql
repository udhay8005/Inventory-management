-- Wipe the 5 demo products + every record that references them.
--
-- The ORM-level ACL lockdown (perm_unlink=0) protects production
-- data from accidental deletion. For an INTENTIONAL purge of demo
-- data we step outside the ORM and do it at SQL, where the postgres
-- 'odoo' role still has the rights it was granted at install time.
--
-- Why SQL instead of ORM:
--   * Bypasses perm_unlink=0 cleanly without softening the policy.
--   * stock.move records in state='done' refuse Odoo-level unlink
--     ("going back in time to revert all operations"); SQL deletes
--     them because there's nothing to revert -- we're clearing a
--     never-shipped demo dataset.
--   * Postgres foreign-key CASCADE / explicit DELETE order catches
--     missed dependencies the Python helper would just silently
--     skip.
--
-- Order is LEAVES FIRST so each DELETE has no FK pointing at the
-- rows it's removing.
--
-- Idempotent: re-running after a successful wipe is a no-op
-- (every DELETE matches zero rows).

BEGIN;

-- 1. Snapshot the demo IDs into a scratch table so each later DELETE
--    references the same set without re-querying.
CREATE TEMP TABLE _demo_prods ON COMMIT DROP AS
SELECT pp.id  AS product_id,
       pt.id  AS tmpl_id,
       pt.default_code
  FROM product_product pp
  JOIN product_template pt ON pt.id = pp.product_tmpl_id
 WHERE pt.default_code IN ('DRILL-18V', 'HELMET-01', 'NUT-M4', 'SCRW-M4-20', 'TIE-200');

\echo '-- Demo products found:'
SELECT * FROM _demo_prods;

-- 2. WMS audit-trail rows
DELETE FROM wms_repair_order
 WHERE product_id IN (SELECT product_id FROM _demo_prods);

DELETE FROM wms_damage
 WHERE product_id IN (SELECT product_id FROM _demo_prods);

-- 3. WMS reporting / config rows
DELETE FROM wms_barcode_alias
 WHERE product_id IN (SELECT product_id FROM _demo_prods);

DELETE FROM wms_forecast_history
 WHERE product_id IN (SELECT product_id FROM _demo_prods);
DELETE FROM wms_forecast
 WHERE product_id IN (SELECT product_id FROM _demo_prods);

-- 4. Stock move lines, then moves, then quants, then pickings that
--    become empty.
DELETE FROM stock_move_line
 WHERE product_id IN (SELECT product_id FROM _demo_prods);

-- Capture picking IDs before we destroy the moves
CREATE TEMP TABLE _demo_pickings ON COMMIT DROP AS
SELECT DISTINCT picking_id
  FROM stock_move
 WHERE product_id IN (SELECT product_id FROM _demo_prods)
   AND picking_id IS NOT NULL;

DELETE FROM stock_move
 WHERE product_id IN (SELECT product_id FROM _demo_prods);

DELETE FROM stock_quant
 WHERE product_id IN (SELECT product_id FROM _demo_prods);

-- Pickings that no longer have any moves are orphans -- drop them.
DELETE FROM stock_picking
 WHERE id IN (SELECT picking_id FROM _demo_pickings)
   AND NOT EXISTS (
     SELECT 1 FROM stock_move WHERE stock_move.picking_id = stock_picking.id
   );

-- 5. Mail messages + attachments referencing the demo products
DELETE FROM mail_message
 WHERE (model = 'product.product' AND res_id IN (SELECT product_id FROM _demo_prods))
    OR (model = 'product.template' AND res_id IN (SELECT tmpl_id   FROM _demo_prods));

-- 6. ir_attachment rows (label PDFs, etc.)
DELETE FROM ir_attachment
 WHERE (res_model = 'product.product'  AND res_id IN (SELECT product_id FROM _demo_prods))
    OR (res_model = 'product.template' AND res_id IN (SELECT tmpl_id   FROM _demo_prods));

-- 7. The products themselves
DELETE FROM product_product
 WHERE id IN (SELECT product_id FROM _demo_prods);

DELETE FROM product_template
 WHERE id IN (SELECT tmpl_id FROM _demo_prods);

-- 8. Reset per-kind SKU sequences so the trust's first real entry
--    starts at TOOL-00001 / CONS-00001 / etc.
UPDATE ir_sequence
   SET number_next = 1
 WHERE code IN (
   'wms.sku.raw_material',
   'wms.sku.packaging',
   'wms.sku.fluid',
   'wms.sku.finished_good',
   'wms.sku.wip',
   'wms.sku.consumable',
   'wms.sku.tool',
   'wms.sku.spare'
 );

-- 9. Reset the per-DB PostgreSQL sequence counter (ir_sequence_NNN)
--    that Odoo created lazily on first next_by_code() call. We
--    ALTER ... RESTART instead of DROP - dropping leaves Odoo
--    looking for a sequence that doesn't exist and next_by_code
--    fails with "relation ir_sequence_NNN does not exist".
DO $$
DECLARE
    s record;
BEGIN
    FOR s IN
        SELECT id FROM ir_sequence
         WHERE code LIKE 'wms.sku.%'
    LOOP
        -- Only if the PG sequence already exists (Odoo creates it
        -- on first use); otherwise no need to touch it.
        IF EXISTS (
            SELECT 1 FROM pg_class
             WHERE relkind = 'S'
               AND relname = format('ir_sequence_%s', lpad(s.id::text, 3, '0'))
        ) THEN
            EXECUTE format('ALTER SEQUENCE ir_sequence_%s RESTART WITH 1',
                           lpad(s.id::text, 3, '0'));
        END IF;
    END LOOP;
END $$;

COMMIT;

\echo ''
\echo '-- Verification: should print 0 for each table'
SELECT 'products remaining'         AS what, COUNT(*) FROM product_template WHERE default_code IN ('DRILL-18V','HELMET-01','NUT-M4','SCRW-M4-20','TIE-200')
UNION ALL SELECT 'damages',  COUNT(*) FROM wms_damage     WHERE name LIKE 'DMG/%'
UNION ALL SELECT 'repairs',  COUNT(*) FROM wms_repair_order WHERE name LIKE 'REP/%'
UNION ALL SELECT 'aliases',  COUNT(*) FROM wms_barcode_alias
UNION ALL SELECT 'forecasts', COUNT(*) FROM wms_forecast;

\echo ''
\echo '-- SKU sequences (number_next should all be 1):'
SELECT code, prefix, number_next FROM ir_sequence WHERE code LIKE 'wms.sku.%' ORDER BY code;
