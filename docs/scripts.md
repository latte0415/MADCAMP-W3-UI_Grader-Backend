# SQL 스크립트

## 실행 순서

1. `scripts/db.sql` — 기본 스키마 (runs, nodes, edges)
2. `scripts/create_run_memory.sql` — run_memory 테이블
3. `scripts/db_migration.sql` — depth 컬럼, pending_actions 등 마이그레이션
4. `docs/db_migration_hover.sql` — (필요 시) edges에 `hover` action_type 추가

## 스크립트 용도

| 스크립트 | 용도 |
|----------|------|
| `db.sql` | runs, nodes, edges 기본 스키마 생성 |
| `create_run_memory.sql` | run_memory 테이블 및 GIN 인덱스, updated_at 트리거 |
| `db_migration.sql` | action_value 기본값, nodes depth 컬럼·css_snapshot_ref, edges depth_diff_type, pending_actions 테이블 등 |
| `db_migration_hover.sql` | edges `action_type` CHECK에 `hover` 추가 |
| `clear_all_data.sql` | 테스트용: ui-artifacts 스토리지·runs/nodes/edges 전체 삭제 (주의) |
