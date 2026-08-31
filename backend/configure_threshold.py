import sys
from app.services.feedback import load_policy, save_policy

policy = load_policy()

if len(sys.argv) == 1:
    print("=" * 50)
    print("  CURRENT POLICY (thresholds)")
    print("=" * 50)
    for k, v in policy.items():
        print(f"  {k}: {v}")
    print()
    print("  To change thresholds:")
    print("  python3 configure_threshold.py stage2_auto_threshold 0.85")
elif len(sys.argv) == 3:
    key = sys.argv[1]
    value = float(sys.argv[2])
    if key not in policy:
        print(f"Unknown key: {key}. Available: {list(policy.keys())}")
    else:
        old_value = policy[key]
        policy[key] = value
        save_policy(policy)
        print(f"Updated {key}: {old_value} -> {value}")
else:
    print("Usage: python3 configure_threshold.py [key] [value]")
