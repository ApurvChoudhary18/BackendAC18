"""
ShadowShift - AI Stub (Baseline)
- Simple TF-IDF + NearestNeighbors over serialized thread "state"
- Predicts an action from: ["reply", "reply_urgent", "follow_up", "summarize"]
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


class AIStub:
    def __init__(self, ngram_range=(1, 2), n_neighbors: int = 1):
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.nn: Optional[NearestNeighbors] = None
        self.actions: Optional[list[str]] = None
        self.fitted: bool = False
        self._ngram_range = ngram_range
        self._n_neighbors = n_neighbors

    def predict_with_threshold(self, state: str, threshold: float = 0.5) -> Dict[str, Any]:
        pred = self.predict(state)
        if pred["confidence"] < threshold:
            return {"action": "ask_clarification", "confidence": pred["confidence"]}
        return pred

    # ---- Training ----
    def fit(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Expects df with columns: ["state", "action"]
        """
        if "state" not in df.columns or "action" not in df.columns:
            raise ValueError("DataFrame must contain 'state' and 'action' columns")

        texts = df["state"].astype(str).tolist()
        self.actions = df["action"].astype(str).tolist()

        self.vectorizer = TfidfVectorizer(
        ngram_range=self._ngram_range,
        min_df=1,
        max_df=0.95,
    )
        X = self.vectorizer.fit_transform(texts).astype("float32")


        self.nn = NearestNeighbors(n_neighbors=self._n_neighbors, metric="cosine").fit(X)
        self.fitted = True
        return {"num_examples": len(texts), "classes": sorted(set(self.actions))}

    # ---- Inference ----
    def predict(self, state: str) -> Dict[str, Any]:
        if not self.fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        Xq = self.vectorizer.transform([state])
        dist, idx = self.nn.kneighbors(Xq)
        i = int(idx[0][0])
        score = 1 - float(dist[0][0])  # cosine similarity → confidence-ish
        return {"action": self.actions[i], "confidence": score}

    def batch_predict(self, states: List[str]) -> List[Dict[str, Any]]:
        return [self.predict(s) for s in states]

    # ---- Persistence ----
    def save(self, path: str | Path):
        """Persist fitted model to disk."""
        if not self.fitted:
            raise RuntimeError("Model not fitted; cannot save.")
        blob = {
            "vectorizer": self.vectorizer,
            "nn": self.nn,
            "actions": self.actions,
            "ngram_range": self._ngram_range,
            "n_neighbors": self._n_neighbors,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(blob, path)

    @classmethod
    def load(cls, path: str | Path) -> "AIStub":
        """Load model from disk."""
        blob = joblib.load(path)
        obj = cls(ngram_range=blob["ngram_range"], n_neighbors=blob["n_neighbors"])
        obj.vectorizer = blob["vectorizer"]
        obj.nn = blob["nn"]
        obj.actions = blob["actions"]
        obj.fitted = True
        return obj
