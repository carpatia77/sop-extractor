import json
import os
import collections

def append_run(record: dict, log_path: str = "runs.jsonl"):
    # Always append as a single line JSON
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')

def tail_log(log_path: str = "runs.jsonl", n: int = 10):
    if not os.path.exists(log_path):
        print(f"Log {log_path} not found.")
        return
        
    lines = []
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    recent = lines[-n:] if n > 0 else lines
    records = []
    for line in recent:
        if line.strip():
            records.append(json.loads(line.strip()))
            
    # Keep track of previous for regression alerts
    # We need the full history for accurate regression detection per skill
    all_records = []
    for line in lines:
        if line.strip():
            all_records.append(json.loads(line.strip()))
            
    # Map set -> list of records to find previous
    set_history = collections.defaultdict(list)
    for r in all_records:
        set_history[r.get('set', 'unknown')].append(r)
        
    print(f"--- Last {len(records)} runs ---")
    for r in records:
        ts = r.get('ts')
        set_name = r.get('set', 'unknown')
        evo = r.get('evolution', 'N/A')
        unv_pct = r.get('unverified_claims_pct')
        
        print(f"[{ts}] Set: {set_name} | Evolution: {evo}", end="")
        if unv_pct is not None:
            print(f" | Unverified: {unv_pct*100:.1f}%", end="")
        print()
        
        for skill_id, stats in r.get('per_skill', {}).items():
            det = stats.get('determinism_pct')
            flags = stats.get('concept_flags')
            coh = stats.get('coherence')
            
            print(f"    Skill: {skill_id}", end="")
            if det is not None: print(f" | Det: {det*100:.1f}%", end="")
            if flags is not None: print(f" | Flags: {flags}", end="")
            if coh is not None: print(f" | Coh: {coh}", end="")
            print()
            
    print("\n--- Regression Alerts ---")
    alerts = 0
    # Check the very last run for each set against its previous run
    # If the user asks for regressions, we just check the most recent in the log
    for set_name, hist in set_history.items():
        if len(hist) < 2:
            continue
            
        current = hist[-1]
        previous = hist[-2]
        
        # Check unverified claims pct
        curr_unv = current.get('unverified_claims_pct')
        prev_unv = previous.get('unverified_claims_pct')
        if curr_unv is not None and prev_unv is not None:
            if curr_unv - prev_unv > 0.1:
                print(f"⚠️  ALERT: {set_name} evolution unverified claims rose by >10% ({prev_unv*100:.1f}% -> {curr_unv*100:.1f}%)")
                alerts += 1
                
        # Check determinism per skill
        curr_skills = current.get('per_skill', {})
        prev_skills = previous.get('per_skill', {})
        
        for skill_id, c_stats in curr_skills.items():
            if skill_id in prev_skills:
                c_det = c_stats.get('determinism_pct')
                p_det = prev_skills[skill_id].get('determinism_pct')
                
                if c_det is not None and p_det is not None:
                    if p_det - c_det > 0.1:
                        print(f"⚠️  ALERT: Skill {skill_id} in {set_name} determinism dropped by >10% ({p_det*100:.1f}% -> {c_det*100:.1f}%)")
                        alerts += 1

    if alerts == 0:
        print("✅ No regressions detected in latest runs.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tail", type=int, default=10, help="Number of recent runs to show")
    parser.add_argument("--log", default="runs.jsonl", help="Path to runs.jsonl")
    args = parser.parse_args()
    tail_log(args.log, args.tail)
