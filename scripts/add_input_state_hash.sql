-- Migration: Add input_state_hash to nodes table
-- Purpose: Distinguish nodes based on input field values (e.g., form fields with different values)
-- Date: 2026-01-26

-- 1) Add input_state_hash column to nodes table
ALTER TABLE nodes
    ADD COLUMN IF NOT EXISTS input_state_hash VARCHAR(64) NOT NULL DEFAULT '';

-- 2) Update existing nodes with empty input_state_hash (for nodes created before this migration)
-- This ensures all existing nodes have a valid hash value
UPDATE nodes
SET input_state_hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'  -- SHA-256 of empty string
WHERE input_state_hash = '' OR input_state_hash IS NULL;

-- 3) Drop old unique constraint if exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'nodes_unique_state'
    ) THEN
        ALTER TABLE nodes DROP CONSTRAINT nodes_unique_state;
    END IF;
END $$;

-- 4) Add new unique constraint including input_state_hash
ALTER TABLE nodes
    ADD CONSTRAINT nodes_unique_state UNIQUE (
        run_id, url_normalized, a11y_hash, state_hash, input_state_hash
    );

-- 5) Add index for input_state_hash queries (optional, but recommended)
CREATE INDEX IF NOT EXISTS idx_nodes_input_state_hash ON nodes(input_state_hash);

-- 6) Add composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_nodes_run_input_state ON nodes(run_id, input_state_hash);
