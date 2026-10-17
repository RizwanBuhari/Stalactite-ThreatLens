"""Ranking and multi-label metrics, at technique level and parent-technique level."""

import numpy as np


def to_parent(ids):
    return list(dict.fromkeys(i.split(".")[0] for i in ids))


def ranked_ids(scores, labels, k):
    order = np.argsort(-scores, axis=1)[:, :k]
    return [[labels[j] for j in row] for row in order]


def parent_ranking(scores, labels, k):
    """Parent score = best child score; ranks parents without duplicates."""
    parents = sorted({l.split(".")[0] for l in labels})
    idx = {p: i for i, p in enumerate(parents)}
    ps = np.zeros((scores.shape[0], len(parents)))
    for j, l in enumerate(labels):
        col = idx[l.split(".")[0]]
        ps[:, col] = np.maximum(ps[:, col], scores[:, j])
    return ps, parents


def evaluate(scores, labels, gold, threshold, ks=(1, 3, 5)):
    """gold: list of label lists. Returns hit@k, recall@3, micro/macro F1 at threshold."""
    n = len(gold)
    top = ranked_ids(scores, labels, max(ks))
    out = {"rows": n}
    for k in ks:
        out[f"hit@{k}"] = round(sum(bool(set(t[:k]) & set(g)) for t, g in zip(top, gold)) / n, 4)
    out["recall@3"] = round(float(np.mean([len(set(t[:3]) & set(g)) / len(g) for t, g in zip(top, gold)])), 4)
    # Threshold predictions; always keep the top-1 so every row gets an answer.
    tp = fp = fn = 0
    per = {}
    for i, g in enumerate(gold):
        pred = {labels[j] for j in np.where(scores[i] >= threshold)[0]} | {top[i][0]}
        g = set(g)
        for l in pred | g:
            a = per.setdefault(l, [0, 0, 0])
            a[0] += l in pred and l in g
            a[1] += l in pred and l not in g
            a[2] += l in g and l not in pred
        tp += len(pred & g); fp += len(pred - g); fn += len(g - pred)
    out["micro_f1"] = round(2 * tp / max(2 * tp + fp + fn, 1), 4)
    f1s = [2 * a[0] / (2 * a[0] + a[1] + a[2]) for l, a in per.items() if any(l in set(g) for g in gold)]
    out["macro_f1"] = round(float(np.mean(f1s)) if f1s else 0.0, 4)
    return out


def best_threshold(scores, labels, gold):
    best = (0.0, 0.5)
    for t in np.arange(0.05, 0.75, 0.05):
        f = evaluate(scores, labels, gold, t, ks=(1,))["micro_f1"]
        best = max(best, (f, round(float(t), 2)))
    return best[1]
