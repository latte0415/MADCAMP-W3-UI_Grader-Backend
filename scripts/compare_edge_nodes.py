#!/usr/bin/env python3
"""edges.id를 입력받아 from_node와 to_node의 차이점을 출력하는 스크립트"""
import sys
import json
from uuid import UUID
from typing import Optional, Dict, Any

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, '/Users/laxogud/MADCAMP/W3/backend')

from repositories.edge_repository import get_edge_by_id
from repositories.node_repository import get_node_by_id


def format_value(value: Any) -> str:
    """값을 보기 좋게 포맷팅"""
    if value is None:
        return "None"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def compare_nodes(from_node: Optional[Dict], to_node: Optional[Dict]) -> None:
    """두 노드의 차이점을 출력"""
    print("=" * 80)
    print("노드 비교 결과")
    print("=" * 80)
    
    if not from_node:
        print("❌ from_node를 찾을 수 없습니다.")
        return
    
    if not to_node:
        print("❌ to_node를 찾을 수 없습니다.")
        return
    
    # 비교할 필드 목록
    fields_to_compare = [
        "id",
        "url",
        "url_normalized",
        "a11y_hash",
        "state_hash",
        "input_state_hash",
        "auth_state",
        "storage_fingerprint",
        "route_depth",
        "modal_depth",
        "interaction_depth",
        "created_at"
    ]
    
    print(f"\n📌 From Node ID: {from_node.get('id')}")
    print(f"📌 To Node ID: {to_node.get('id')}")
    print()
    
    differences = []
    same_fields = []
    
    for field in fields_to_compare:
        from_value = from_node.get(field)
        to_value = to_node.get(field)
        
        if from_value != to_value:
            differences.append(field)
            print(f"🔴 차이점: {field}")
            print(f"   From: {format_value(from_value)}")
            print(f"   To:   {format_value(to_value)}")
            print()
        else:
            same_fields.append(field)
    
    print("-" * 80)
    print(f"✅ 동일한 필드 ({len(same_fields)}개): {', '.join(same_fields)}")
    print(f"🔴 다른 필드 ({len(differences)}개): {', '.join(differences) if differences else '없음'}")
    print("=" * 80)


def main():
    """메인 함수"""
    if len(sys.argv) < 2:
        print("사용법: python compare_edge_nodes.py <edge_id>")
        print("예시: python compare_edge_nodes.py 123e4567-e89b-12d3-a456-426614174000")
        sys.exit(1)
    
    edge_id_str = sys.argv[1]
    
    try:
        edge_id = UUID(edge_id_str)
    except ValueError:
        print(f"❌ 잘못된 UUID 형식: {edge_id_str}")
        sys.exit(1)
    
    # 엣지 조회
    print(f"🔍 엣지 조회 중: {edge_id}")
    edge = get_edge_by_id(edge_id)
    
    if not edge:
        print(f"❌ 엣지를 찾을 수 없습니다: {edge_id}")
        sys.exit(1)
    
    print(f"✅ 엣지 찾음")
    print(f"   Action: {edge.get('action_type')} / {edge.get('action_target', '')[:50]}")
    print(f"   Outcome: {edge.get('outcome')}")
    print()
    
    # 노드 조회
    from_node_id_str = edge.get('from_node_id')
    to_node_id_str = edge.get('to_node_id')
    
    if not from_node_id_str:
        print("❌ from_node_id가 없습니다.")
        sys.exit(1)
    
    from_node_id = UUID(from_node_id_str)
    from_node = get_node_by_id(from_node_id)
    
    if not from_node:
        print(f"❌ from_node를 찾을 수 없습니다: {from_node_id}")
        sys.exit(1)
    
    to_node = None
    if to_node_id_str:
        to_node_id = UUID(to_node_id_str)
        to_node = get_node_by_id(to_node_id)
        
        if not to_node:
            print(f"⚠️  to_node를 찾을 수 없습니다: {to_node_id}")
            print("   (액션이 실패했거나 같은 노드로 돌아온 경우일 수 있습니다)")
            print()
    
    # 노드 비교
    compare_nodes(from_node, to_node)


if __name__ == "__main__":
    main()
