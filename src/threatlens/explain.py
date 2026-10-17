"""Passage-level suggestions with word-level evidence from the model itself.

For each suggested technique we show the sentence that scored highest and the
words in it that pushed the score up most (TF-IDF value x logistic-regression
weight). The evidence is computed from the model, not generated.
"""

import re

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(\[])|\n+")


def split_sentences(text):
    parts = [p.strip() for p in SENTENCE.split(text) if p and p.strip()]
    return [p for p in parts if len(re.findall(r"\w+", p)) >= 3] or [text.strip()]


class Explainer:
    def __init__(self, model):
        self.model = model
        self.terms = model.word.get_feature_names_out()
        self.n_word = len(self.terms)
        # One weight row per technique, word features only (readable n-grams).
        self.weights = np.vstack([est.coef_[0][: self.n_word] for est in model.clf.estimators_])

    def evidence_terms(self, sentence, label_index, top=4):
        x = self.model.word.transform([sentence])
        idx, vals = x.indices, x.data
        contrib = vals * self.weights[label_index, idx]
        order = np.argsort(-contrib)
        terms = []
        for i in order:
            term = self.terms[idx[i]]
            if contrib[i] <= 0 or len(terms) == top:
                break
            if all(w in ENGLISH_STOP_WORDS for w in term.split()):
                continue                                  # 'from', 'to the' carry no evidence
            term = " ".join(w for w in term.split() if w not in ENGLISH_STOP_WORDS)
            if term not in terms:
                terms.append(term)
        # Drop a unigram already covered by a chosen bigram.
        return [t for t in terms if not any(t != o and t in o.split() for o in terms)]

    def suggest(self, text, k=3, alternatives=10):
        sentences = split_sentences(text)
        scores = self.model.scores(sentences)            # (n_sentences, n_labels)
        best = scores.max(axis=0)
        where = scores.argmax(axis=0)
        order = np.argsort(-best)
        out = []
        for rank, j in enumerate(order[: max(k, alternatives)]):
            sent_i = int(where[j])
            item = {"technique_id": self.model.labels_[j], "score": round(float(best[j]), 4),
                    "sentence_index": sent_i}
            if rank < k:
                item["evidence"] = sentences[sent_i]
                item["evidence_terms"] = self.evidence_terms(sentences[sent_i], j)
            out.append(item)
        return sentences, out[:k], out[k:]
