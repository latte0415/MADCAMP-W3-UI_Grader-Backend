-- Migration: allow hover action type
-- Run after previous migrations

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'edges_action_type_check'
    ) THEN
        ALTER TABLE edges DROP CONSTRAINT edges_action_type_check;
    END IF;
END $$;

ALTER TABLE edges
    ADD CONSTRAINT edges_action_type_check
    CHECK (action_type IN ('click', 'fill', 'navigate', 'scroll', 'keyboard', 'wait', 'hover'));
