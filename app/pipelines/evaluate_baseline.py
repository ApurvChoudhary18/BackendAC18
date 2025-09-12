from pathlib import Path
import sys
import warnings
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

warnings.filterwarnings("ignore")  # keep output clean for tiny datasets

ROOT = Path(__file__).resolve().parents[2]   # .../backend
PROJ = ROOT.parent
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from backend.app.models.ai_stub import AIStub  # noqa: E402


def try_grouped_split(df: pd.DataFrame, test_size=0.4, max_tries=25, random_state=42):
    """Split by thread_id (groups) but try to keep same label set in train and test."""
    groups = df["thread_id"]
    labels = df["action"]

    gss = GroupShuffleSplit(n_splits=max_tries, test_size=test_size, random_state=random_state)
    for tr_idx, te_idx in gss.split(df, groups=groups):
        tr_labels = set(labels.iloc[tr_idx])
        te_labels = set(labels.iloc[te_idx])
        # require at least 1 label in test and test label-set ⊆ train label-set
        if te_labels and te_labels.issubset(tr_labels):
            return df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx].reset_index(drop=True)

    # Fallback: take the last split even if imperfect
    tr_idx, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state).split(df, groups=groups))
    return df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx].reset_index(drop=True)


def main():
    ds = ROOT / "data" / "processed" / "dataset.parquet"
    if not ds.exists():
        raise SystemExit(f"Dataset not found: {ds}")

    df = pd.read_parquet(ds)
    if df.empty:
        raise SystemExit("Dataset empty.")

    # Diagnostics
    print("Total rows:", len(df))
    print("Label counts:\n", df["action"].value_counts())
    print("Threads:", df["thread_id"].nunique(), "→", df["thread_id"].unique().tolist())

    # Split
    train, test = try_grouped_split(df, test_size=0.4)

    print("\nTrain size:", len(train), "| Test size:", len(test))
    print("Train labels:\n", train["action"].value_counts())
    print("Test labels:\n", test["action"].value_counts())

    # Fit + Eval
    model = AIStub()
    model.fit(train)

    y_true = test["action"].tolist()
    y_pred = [model.predict(s)["action"] for s in test["state"].tolist()]

    print("\nAccuracy:", round(accuracy_score(y_true, y_pred), 3))
    print("Confusion Matrix:\n", confusion_matrix(y_true, y_pred, labels=sorted(df["action"].unique())))
    print("Report:\n", classification_report(y_true, y_pred, zero_division=0))

if __name__ == "__main__":
    main()
