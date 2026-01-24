-- Migration for graph depth metadata
-- Assumes nodes/edges tables already exist.

-- 1) action_value default and normalize NULLs
ALTER TABLE edges
    ALTER COLUMN action_value SET DEFAULT '';

UPDATE edges
SET action_value = ''
WHERE action_value IS NULL;

-- 2) add depth columns to nodes
ALTER TABLE nodes
    ADD COLUMN IF NOT EXISTS route_depth INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS modal_depth INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS interaction_depth INT DEFAULT 0;

-- 2.1) add css snapshot ref to nodes
ALTER TABLE nodes
    ADD COLUMN IF NOT EXISTS css_snapshot_ref TEXT;

-- 3) remove old change_type constraint if exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'edges_change_type_check'
    ) THEN
        -- no-op
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'edges_change_type_check'
    ) THEN
        ALTER TABLE edges DROP CONSTRAINT edges_change_type_check;
    END IF;
END $$;

-- 4) drop old depth columns on edges if exist
ALTER TABLE edges
    DROP COLUMN IF EXISTS change_type,
    DROP COLUMN IF EXISTS route_depth,
    DROP COLUMN IF EXISTS modal_depth,
    DROP COLUMN IF EXISTS interaction_depth;

-- 5) add depth_diff_type to edges
ALTER TABLE edges
    ADD COLUMN IF NOT EXISTS depth_diff_type VARCHAR(30);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'edges_depth_diff_type_check'
    ) THEN
        ALTER TABLE edges
            ADD CONSTRAINT edges_depth_diff_type_check
            CHECK (depth_diff_type IN ('same_node', 'interaction_only', 'new_page', 'modal_overlay', 'drawer'));
    END IF;
END $$;

-- 6) update unique constraint (remove COALESCE)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'edges_dedupe'
    ) THEN
        ALTER TABLE edges DROP CONSTRAINT edges_dedupe;
    END IF;
END $$;

ALTER TABLE edges
    ADD CONSTRAINT edges_dedupe UNIQUE (
        run_id, from_node_id, to_node_id, action_type, action_target, action_value
    );

-- 7) optional indexes for depth queries
CREATE INDEX IF NOT EXISTS idx_edges_depth_diff_type ON edges(depth_diff_type);
CREATE INDEX IF NOT EXISTS idx_nodes_route_depth ON nodes(route_depth);
CREATE INDEX IF NOT EXISTS idx_nodes_modal_depth ON nodes(modal_depth);
CREATE INDEX IF NOT EXISTS idx_nodes_interaction_depth ON nodes(interaction_depth);
