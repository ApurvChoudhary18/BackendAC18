from pathlib import Path
import sys
import pandas as pd

# Ensure project root is on sys.path so "backend.app..." imports work
ROOT = Path(__file__).resolve().parents[2]   # -> .../shadowshift/backend
PROJECT_ROOT = ROOT.parent                   # -> .../shadowshift
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.models.ai_stub import AIStub  # noqa: E402


def main():
    ds_path = ROOT / "data" / "processed" / "dataset.parquet"
    if not ds_path.exists():
        raise SystemExit(f"Dataset not found: {ds_path}\n"
                         "Run build first: python backend/app/pipelines/build_dataset_fast.py")

    df = pd.read_parquet(ds_path)
    if df.empty:
        raise SystemExit("Dataset is empty. Check your events.jsonl and rules.")

    model = AIStub()
    info = model.fit(df)
    print("AIStub fitted:", info)

    # quick smoke test
    query_state = (
        "[Thread: demo | Sources: gmail, github]\n"
        "2025-08-21 10:00 other: can you merge this? need it by EOD\n"
        "2025-08-21 10:05 you: will do\n"
    )
    print("PRED:", model.predict(query_state))
    print("PRED(th=0.5):", model.predict_with_threshold(query_state, threshold=0.5))



if __name__ == "__main__":
    main()
