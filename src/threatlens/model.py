"""Baseline technique ranker: TF-IDF (word + character n-grams) + one-vs-rest logistic regression."""

import time

import joblib
import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer


def split_ids(s):
    return [i for i in s.split(";") if i]


class TechniqueRanker:
    def __init__(self, C=4.0, min_support=3, n_jobs=3):
        self.C, self.min_support, self.n_jobs = C, min_support, n_jobs
        self.word = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=150_000,
                                    sublinear_tf=True, strip_accents="unicode")
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3,
                                    max_features=150_000, sublinear_tf=True)
        self.threshold = 0.5

    def _features(self, texts, fit=False):
        if fit:
            X = hstack([self.word.fit_transform(texts), self.char.fit_transform(texts)]).tocsr()
        else:
            X = hstack([self.word.transform(texts), self.char.transform(texts)]).tocsr()
        # Parallel workers receive a read-only copy and cannot sort it themselves.
        X.sum_duplicates()
        X.sort_indices()
        return X

    def fit(self, texts, label_lists):
        counts = {}
        for ls in label_lists:
            for t in ls:
                counts[t] = counts.get(t, 0) + 1
        self.labels_ = sorted(t for t, c in counts.items() if c >= self.min_support)
        keep = set(self.labels_)
        self.mlb = MultiLabelBinarizer(classes=self.labels_)
        y = self.mlb.fit_transform([[t for t in ls if t in keep] for ls in label_lists])
        X = self._features(texts, fit=True)
        self.clf = OneVsRestClassifier(
            LogisticRegression(C=self.C, solver="liblinear", max_iter=1000), n_jobs=self.n_jobs)
        t0 = time.perf_counter()
        self.clf.fit(X, y)
        self.fit_seconds_ = time.perf_counter() - t0
        self.n_features_ = X.shape[1]
        return self

    def scores(self, texts):
        """Independent per-technique probabilities, shape (n_texts, n_labels)."""
        return self.clf.predict_proba(self._features(texts))

    def rank(self, texts, k=3):
        s = self.scores(texts)
        top = np.argsort(-s, axis=1)[:, :k]
        return [[(self.labels_[j], float(s[i, j])) for j in row] for i, row in enumerate(top)]

    def save(self, path):
        joblib.dump(self, path, compress=3)

    @staticmethod
    def load(path):
        return joblib.load(path)
