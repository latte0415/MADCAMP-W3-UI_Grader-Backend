#!/usr/bin/env python3
"""edges.id를 입력받아 액션 실행 후 실제 페이지 상태와 to_node를 비교하는 스크립트"""
import sys
import json
import asyncio
from uuid import UUID
from typing import Optional, Dict, Any

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, '/Users/laxogud/MADCAMP/W3/backend')

from playwright.async_api import async_playwright
from repositories.edge_repository import get_edge_by_id
from repositories.node_repository import get_node_by_id
from infra.supabase import download_storage_file
from utils.state_collector import collect_page_state
from utils.hash_generator import (
    normalize_url,
    generate_storage_fingerprint,
    generate_state_hash,
    generate_a11y_hash,
    generate_content_dom_hash,
    generate_input_state_hash
)
from services.edge_service import EdgeService


def format_value(value: Any) -> str:
    """값을 보기 좋게 포맷팅"""
    if value is None:
        return "None"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def compare_actual_vs_to_node(actual_page_state: Dict, to_node: Optional[Dict]) -> None:
    """실제 페이지 상태와 to_node를 비교"""
    print("=" * 80)
    print("실제 액션 실행 후 페이지 상태 vs to_node 비교")
    print("=" * 80)
    
    if not to_node:
        print("❌ to_node를 찾을 수 없습니다.")
        print("\n📌 실제 페이지 상태:")
        print(f"   URL: {actual_page_state.get('url')}")
        print(f"   URL Normalized: {normalize_url(actual_page_state.get('url', ''))}")
        print(f"   A11y Hash: {actual_page_state.get('a11y_hash')}")
        print(f"   State Hash: {actual_page_state.get('state_hash')}")
        print(f"   Input State Hash: {actual_page_state.get('input_state_hash')}")
        return
    
    # 실제 페이지 상태에서 해시 계산
    actual_url = actual_page_state.get("url", "")
    actual_url_normalized = normalize_url(actual_url)
    actual_storage_state = actual_page_state.get("storage_state", {})
    actual_storage_fingerprint = generate_storage_fingerprint(
        actual_storage_state.get("localStorage", {}),
        actual_storage_state.get("sessionStorage", {})
    )
    actual_auth_state = actual_page_state.get("auth_state", {})
    actual_state_hash = generate_state_hash(actual_auth_state, actual_storage_fingerprint)
    actual_a11y_info = actual_page_state.get("a11y_info", [])
    actual_a11y_hash = generate_a11y_hash(actual_a11y_info)
    actual_content_elements = actual_page_state.get("content_elements", [])
    actual_content_dom_hash = generate_content_dom_hash(actual_content_elements)
    actual_input_values = actual_page_state.get("input_values", {})
    actual_input_state_hash = generate_input_state_hash(actual_input_values)
    
    print(f"\n📌 To Node ID: {to_node.get('id')}")
    print()
    
    # 비교할 필드 목록
    comparisons = [
        ("url", actual_url, to_node.get("url")),
        ("url_normalized", actual_url_normalized, to_node.get("url_normalized")),
        ("a11y_hash", actual_a11y_hash, to_node.get("a11y_hash")),
        ("state_hash", actual_state_hash, to_node.get("state_hash")),
        ("input_state_hash", actual_input_state_hash, to_node.get("input_state_hash")),
        ("content_dom_hash", actual_content_dom_hash, to_node.get("content_dom_hash")),
    ]
    
    differences = []
    same_fields = []
    
    for field_name, actual_value, to_node_value in comparisons:
        if actual_value != to_node_value:
            differences.append(field_name)
            print(f"🔴 차이점: {field_name}")
            print(f"   실제 페이지: {format_value(actual_value)}")
            print(f"   To Node:     {format_value(to_node_value)}")
            print()
        else:
            same_fields.append(field_name)
    
    # 상세 비교 (auth_state, storage_fingerprint)
    print("-" * 80)
    print("상세 비교:")
    print("-" * 80)
    
    # auth_state 비교
    actual_auth = actual_auth_state
    to_node_auth = to_node.get("auth_state", {})
    if actual_auth != to_node_auth:
        print("🔴 auth_state 차이:")
        print(f"   실제 페이지: {format_value(actual_auth)}")
        print(f"   To Node:     {format_value(to_node_auth)}")
        print()
    else:
        print("✅ auth_state 동일")
        print()
    
    # storage_fingerprint 비교
    actual_storage = actual_storage_fingerprint
    to_node_storage = to_node.get("storage_fingerprint", {})
    if actual_storage != to_node_storage:
        print("🔴 storage_fingerprint 차이:")
        print(f"   실제 페이지: {format_value(actual_storage)}")
        print(f"   To Node:     {format_value(to_node_storage)}")
        print()
    else:
        print("✅ storage_fingerprint 동일")
        print()
    
    print("-" * 80)
    print(f"✅ 동일한 필드 ({len(same_fields)}개): {', '.join(same_fields)}")
    print(f"🔴 다른 필드 ({len(differences)}개): {', '.join(differences) if differences else '없음'}")
    
    if differences:
        print("\n⚠️  경고: 실제 페이지 상태와 to_node가 다릅니다!")
        print("   액션 실행 후 실제로 이동한 페이지가 to_node와 일치하지 않을 수 있습니다.")
    else:
        print("\n✅ 실제 페이지 상태와 to_node가 일치합니다.")
    
    print("=" * 80)


async def restore_node_state(page, from_node: Dict) -> None:
    """노드 상태 복원 (storage_state, input_values)"""
    # storage_state 복원
    storage_ref = from_node.get("storage_ref")
    if storage_ref:
        try:
            storage_bytes = download_storage_file(storage_ref)
            storage_state = json.loads(storage_bytes.decode("utf-8"))
            
            # Playwright의 storage_state 형식으로 변환
            # storage_state는 cookies, origins 등을 포함
            await page.context.add_cookies(storage_state.get("cookies", []))
            
            # localStorage와 sessionStorage 복원
            for origin in storage_state.get("origins", []):
                origin_url = origin.get("origin", "")
                if origin_url:
                    # localStorage 복원
                    local_storage = origin.get("localStorage", [])
                    for item in local_storage:
                        key = item.get("name")
                        value = item.get("value")
                        if key and value:
                            await page.evaluate(
                                f"localStorage.setItem('{key}', {json.dumps(value)})",
                                origin_url
                            )
                    
                    # sessionStorage 복원
                    session_storage = origin.get("sessionStorage", [])
                    for item in session_storage:
                        key = item.get("name")
                        value = item.get("value")
                        if key and value:
                            await page.evaluate(
                                f"sessionStorage.setItem('{key}', {json.dumps(value)})",
                                origin_url
                            )
        except Exception as e:
            print(f"⚠️  storage_state 복원 실패 (계속 진행): {e}")
    
    # input_values 복원
    dom_ref = from_node.get("dom_snapshot_ref")
    if dom_ref:
        try:
            input_state_ref = dom_ref.replace("dom_snapshot.html", "input_state.json")
            input_bytes = download_storage_file(input_state_ref)
            input_values = json.loads(input_bytes.decode("utf-8"))
            
            # 입력값 복원 (간단한 방법 - 실제로는 action_extractor를 사용해야 함)
            # 여기서는 기본적인 복원만 수행
            for action_target, value in input_values.items():
                try:
                    # role과 name 파싱 시도
                    if action_target.startswith("role="):
                        parts = action_target.split(" name=")
                        if len(parts) == 2:
                            role = parts[0].replace("role=", "").strip()
                            name = parts[1].strip()
                            if role and name:
                                locator = page.get_by_role(role, name=name)
                                if await locator.count() > 0:
                                    await locator.fill(value)
                                    continue
                    
                    # selector 사용
                    if not action_target.startswith("role="):
                        await page.fill(action_target, value)
                except Exception as e:
                    # 입력값 복원 실패는 무시 (선택적)
                    pass
        except Exception as e:
            # input_state가 없거나 복원 실패는 무시
            pass


async def main_async():
    """비동기 메인 함수"""
    if len(sys.argv) < 2:
        print("사용법: python compare_edge_actual_vs_to_node.py <edge_id>")
        print("예시: python compare_edge_actual_vs_to_node.py 123e4567-e89b-12d3-a456-426614174000")
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
    
    print(f"✅ From Node 찾음: {from_node.get('url')}")
    
    to_node = None
    if to_node_id_str:
        to_node_id = UUID(to_node_id_str)
        to_node = get_node_by_id(to_node_id)
        
        if to_node:
            print(f"✅ To Node 찾음: {to_node.get('url')}")
        else:
            print(f"⚠️  to_node를 찾을 수 없습니다: {to_node_id}")
    else:
        print("⚠️  to_node_id가 없습니다 (액션이 실패했거나 같은 노드로 돌아온 경우)")
    
    print()
    
    # 액션 정보 구성
    action = {
        "action_type": edge.get("action_type"),
        "action_target": edge.get("action_target"),
        "action_value": edge.get("action_value", ""),
        "role": None,  # edge에 저장되지 않았을 수 있음
        "name": None,
        "selector": None,
        "href": None
    }
    
    # action_target에서 role과 name 파싱 시도
    action_target = action.get("action_target", "")
    if action_target.startswith("role="):
        parts = action_target.split(" name=")
        if len(parts) == 2:
            action["role"] = parts[0].replace("role=", "").strip()
            action["name"] = parts[1].strip()
    else:
        action["selector"] = action_target
    
    # Playwright로 실제 액션 실행
    print("🌐 브라우저 시작 중...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 디버깅을 위해 headless=False
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # from_node 상태로 복원
            print(f"📥 From Node 상태 복원 중: {from_node.get('url')}")
            await page.goto(from_node.get("url"), wait_until="networkidle")
            await restore_node_state(page, from_node)
            
            # 페이지 안정화 대기
            await page.wait_for_timeout(1000)
            
            # 액션 실행
            print(f"⚡ 액션 실행 중: {action.get('action_type')} / {action.get('action_target', '')[:50]}")
            edge_service = EdgeService()
            action_result = await edge_service.perform_action(page, action)
            
            if action_result["outcome"] != "success":
                print(f"❌ 액션 실행 실패: {action_result.get('error_msg')}")
                await browser.close()
                sys.exit(1)
            
            # 액션 실행 후 페이지 안정화 대기
            await page.wait_for_timeout(2000)
            
            # 실제 페이지 상태 수집
            print("📊 실제 페이지 상태 수집 중...")
            actual_page_state = await collect_page_state(page)
            
            # 해시 계산을 위해 추가 정보 포함
            actual_page_state["a11y_hash"] = generate_a11y_hash(actual_page_state.get("a11y_info", []))
            actual_page_state["state_hash"] = generate_state_hash(
                actual_page_state.get("auth_state", {}),
                generate_storage_fingerprint(
                    actual_page_state.get("storage_state", {}).get("localStorage", {}),
                    actual_page_state.get("storage_state", {}).get("sessionStorage", {})
                )
            )
            actual_page_state["input_state_hash"] = generate_input_state_hash(actual_page_state.get("input_values", {}))
            actual_page_state["content_dom_hash"] = generate_content_dom_hash(actual_page_state.get("content_elements", []))
            
            await browser.close()
            
            # 비교
            compare_actual_vs_to_node(actual_page_state, to_node)
            
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            await browser.close()
            sys.exit(1)


def main():
    """메인 함수"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
