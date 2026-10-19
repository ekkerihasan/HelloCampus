"""Small BM25 (Okapi) index over chunk texts. Names of students, halls, events and restaurants are exact
strings that embeddings often miss, so retrieval fuses this with vector search (ADDENDUM-01 section 7.4)."""
import math
import re
from collections import Counter

STOPWORDS = frozenset("""a an and are as at be by can do does for from has have how i in is it its me my
near nearby of on or our so tell that the their there this to us was what when where which who why will
with you your any some about get go there's is there whats where's please know""".split())
K1 = 1.5
B = 0.75
# Visitor shorthand -> the word campus pages use, applied after plural trimming on both queries and documents.
SYNONYMS = {"stat": "statistic", "stats": "statistic", "lpa": "package", "salary": "package", "hod": "head",
            "dept": "department", "cse": "computer", "ece": "electronic", "eee": "electrical", "mba": "business",
            "mca": "application", "placed": "placement", "hostel": "accommodation", "canteen": "cafeteria"}


def tokenize(text: str) -> list[str]:
    tokens = []
    for t in re.findall(r"\w+", text.lower()):
        if len(t) < 2 or t in STOPWORDS:
            continue
        t = t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t
        tokens.append(SYNONYMS.get(t, t))
    return tokens


class BM25:
    def __init__(self, ids: list[str], texts: list[str]) -> None:
        self.ids = ids
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._unknown_idf = math.log(1 + (n + 0.5) / 0.5) if n else 1.0

    def search(self, query: str, k: int) -> list[tuple[str, float, float]]:
        """Returns (id, bm25 score, keyword coverage) for the top k matching docs.
        Coverage is the IDF-weighted share of query terms present in the doc, used for the refusal gate."""
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms or not self.docs:
            return []
        weights = {t: self.idf.get(t, self._unknown_idf) for t in terms}
        total = sum(weights.values())
        scored = []
        for i, doc in enumerate(self.docs):
            score, matched = 0.0, 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if not tf:
                    continue
                matched += weights[t]
                denom = tf + K1 * (1 - B + B * self.lengths[i] / (self.avg_len or 1))
                score += self.idf.get(t, 0.0) * tf * (K1 + 1) / denom
            if score > 0:
                scored.append((self.ids[i], score, matched / total if total else 0.0))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]
