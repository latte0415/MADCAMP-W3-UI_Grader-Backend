from infra.supabase import get_client, download_storage_file
import json

def inspect_sample_node():
    supabase = get_client()

    # 1. Get the latest run
    runs_result = supabase.table("runs").select("*").order("created_at", desc=True).limit(1).execute()
    if not runs_result.data:
        print("No runs found in the database.")
        return

    latest_run = runs_result.data[0]
    run_id = latest_run["id"]
    print(f"Investigating latest run: {run_id}\n")

    # 2. Get the 3rd node from the last (ordered by id descending)
    nodes_result = supabase.table("nodes").select("*").eq("run_id", run_id).order("id", desc=True).limit(3).execute()
    if not nodes_result.data:
        print(f"No nodes found for run {run_id}.")
        return
    
    if len(nodes_result.data) < 3:
        print(f"Only {len(nodes_result.data)} nodes found. Inspecting the last one available.")
        node = nodes_result.data[-1]
    else:
        node = nodes_result.data[2] # 3rd from the last
    
    # 3. Print node information
    print("=== Sample Node Information ===")
    print(json.dumps(node, indent=2, ensure_ascii=False))

    # 4. Fetch and print a snippet of the actual DOM
    dom_ref = node.get("dom_snapshot_ref")
    if dom_ref:
        try:
            print("\n=== DOM Snapshot Sneak Peek (First 500 chars) ===")
            dom_bytes = download_storage_file(dom_ref)
            print(dom_bytes.decode("utf-8")[:500] + "...")
        except Exception as e:
            print(f"\nError fetching DOM snapshot: {e}")

if __name__ == "__main__":
    inspect_sample_node()
