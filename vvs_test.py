#!/usr/bin/env python3
"""vvs_test.py — attack harness for the embedding-attack-lab boundary service.

Adapts the manual curl/jq recipes in TESTING.md into a single runnable client so
the live deployment (default: https://your-target.example) can be poked smoothly. It
implements the smoke tests (TESTING.md §1–2), the chosen-plaintext K+ capability
(§3), the four measurement attacks a–d (§4), and the boundary checks (§5).

Everything is read-only against the endpoint except the K+ inserts, which post
*attacker-owned* known chunks (never a corpus doc_id) — exactly the modelled
adversary capability the service is built to expose. The numeric analysis
(Spearman ρ, orthogonal Procrustes, AUC) runs client-side.

The service is intentionally unauthenticated; every caller *is* the adversary.
Run only against a deployment you own or are authorized to test.

Deps: requests + numpy (both already in the project env). No scipy/sklearn.

Usage:
    python vvs_test.py smoke
    python vvs_test.py kplus
    python vvs_test.py attack-a            # distance leakage (dump)
    python vvs_test.py attack-b            # Procrustes / known-plaintext
    python vvs_test.py attack-c            # oracle leak (A vs D)
    python vvs_test.py attack-d            # membership inference
    python vvs_test.py boundary            # what must NOT work
    python vvs_test.py all                 # everything except the heavy Procrustes

    python vvs_test.py --base-url https://your-target.example --debug smoke
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Iterable

import numpy as np
import requests

# ─────────────────────────────────────────────────────────────────────────────
#  SETTINGS  — everything the harness adapts to lives here (or via CLI / env).
#  Override any of these with the matching CLI flag or VVS_* environment var.
# ─────────────────────────────────────────────────────────────────────────────
DEFAULTS = {
    "base_url": os.environ.get("VVS_BASE_URL", "https://your-target.example"),
    "arms": os.environ.get("VVS_ARMS", "A,B,C,D").split(","),
    "dim": int(os.environ.get("VVS_DIM", "2560")),        # M1 = Qwen3-Embedding-4B
    "timeout": float(os.environ.get("VVS_TIMEOUT", "30")),
    # arm roles used by the attacks (see TESTING.md §2 and §4)
    "plaintext_arm": "A",   # raw float32 — the plaintext reference
    "searchable_arm": "C",  # distance-preserving transform (Procrustes / ρ target)
    "strong_arm": "D",      # AES-GCM at rest; oracle plane leaks plaintext scores
    "cloaked_arm": "B",     # DPE ciphertext (partial distance leakage)
}

# API contract (TESTING.md §1–3). Centralised so a redeploy with different paths
# only needs edits here.
ROUTES = {
    "healthz": "/healthz",
    "arms": "/arms",
    "embed": "/embed",
    "dump": "/arms/{arm}/dump",
    "oracle": "/arms/{arm}/oracle",
    "chunks": "/arms/{arm}/chunks",
}

# Keys under a dump record's `representation` that may hold a numeric vector.
# The service returns a different shape per arm; we probe these in order.
VECTOR_KEYS = ("vector", "values", "data", "embedding", "transform", "components")


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP client
# ─────────────────────────────────────────────────────────────────────────────
class VVS:
    def __init__(self, base_url: str, timeout: float, debug: bool = False):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.debug = debug
        self.s = requests.Session()

    def _url(self, route: str, **fmt: str) -> str:
        return self.base + ROUTES[route].format(**fmt)

    def _log(self, method: str, url: str, body: Any = None) -> None:
        if self.debug:
            line = f"  → {method} {url}"
            if body is not None:
                blob = json.dumps(body)
                line += f"  {blob[:120]}{'…' if len(blob) > 120 else ''}"
            print(line, file=sys.stderr)

    def get(self, route: str, params: dict | None = None, **fmt: str) -> requests.Response:
        url = self._url(route, **fmt)
        self._log("GET", url)
        return self.s.get(url, params=params, timeout=self.timeout)

    def post(self, route: str, payload: dict, **fmt: str) -> requests.Response:
        url = self._url(route, **fmt)
        self._log("POST", url, payload)
        return self.s.post(url, json=payload, timeout=self.timeout)

    # -- typed convenience wrappers ------------------------------------------
    def healthz(self) -> dict:
        return self.get("healthz").json()

    def arms(self) -> Any:
        return self.get("arms").json()

    def embed(self, text: str) -> np.ndarray:
        r = self.post("embed", {"text": text})
        r.raise_for_status()
        vec = r.json()["vector"]
        return np.asarray(vec, dtype=np.float64)

    def dump(self, arm: str, limit: int) -> list[dict]:
        r = self.get("dump", params={"limit": limit}, arm=arm)
        r.raise_for_status()
        return r.json().get("records", [])

    def oracle(self, arm: str, query: Iterable[float], top_k: int) -> list[dict]:
        r = self.post("oracle", {"query_vector": list(query), "top_k": top_k}, arm=arm)
        r.raise_for_status()
        return r.json().get("results", [])

    def insert_chunk(self, arm: str, text: str) -> dict:
        r = self.post("chunks", {"text": text}, arm=arm)
        r.raise_for_status()
        return r.json()


# ─────────────────────────────────────────────────────────────────────────────
#  helpers
# ─────────────────────────────────────────────────────────────────────────────
def _hr(title: str) -> None:
    print(f"\n=== {title} ===")


def extract_vector(representation: Any) -> np.ndarray | None:
    """Best-effort pull of a numeric vector out of a dump `representation`.

    Arm shapes differ (raw floats, transform, ciphertext tuple, opaque bytes),
    so we try the known keys and fall back to a bare numeric list. Returns None
    when the representation carries no usable numeric vector (e.g. arm D bytes).
    """
    if representation is None:
        return None
    if isinstance(representation, list):
        return _coerce_vector(representation)
    if isinstance(representation, dict):
        for key in VECTOR_KEYS:
            vec = _coerce_vector(representation.get(key))
            if vec is not None:
                return vec
        # some arms nest under representation["payload"] etc. (e.g. the DPE
        # `tuple` arm, whose components are a list of numeric sub-vectors).
        for val in representation.values():
            vec = _coerce_vector(val)
            if vec is not None:
                return vec
    return None


def _coerce_vector(val: Any) -> np.ndarray | None:
    """A flat numeric list, or a list of equal-numeric rows flattened row-major."""
    if not isinstance(val, list) or not val:
        return None
    if _all_numeric(val):
        return np.asarray(val, dtype=np.float64)
    # list of numeric sub-lists (e.g. a ciphertext tuple) -> concatenate
    if all(isinstance(x, list) and _all_numeric(x) for x in val):
        return np.concatenate([np.asarray(x, dtype=np.float64) for x in val])
    return None


def _all_numeric(seq: list) -> bool:
    return len(seq) > 0 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in seq)


def collect_vectors(records: list[dict]) -> tuple[list[str], np.ndarray | None]:
    """Return (doc_ids, matrix) for records that expose a numeric vector."""
    ids, rows = [], []
    for rec in records:
        vec = extract_vector(rec.get("representation"))
        if vec is not None:
            ids.append(rec.get("doc_id"))
            rows.append(vec)
    if not rows:
        return [], None
    width = min(len(r) for r in rows)
    mat = np.vstack([r[:width] for r in rows])
    return ids, mat


def pairwise_distances(mat: np.ndarray) -> np.ndarray:
    """Condensed (upper-triangle) Euclidean pairwise distances."""
    sq = np.sum(mat * mat, axis=1)
    d2 = sq[:, None] + sq[None, :] - 2.0 * (mat @ mat.T)
    d2 = np.maximum(d2, 0.0)
    iu = np.triu_indices(mat.shape[0], k=1)
    return np.sqrt(d2[iu])


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman ρ = Pearson correlation of ranks (average-rank ties)."""
    if a.size < 2:
        return float("nan")
    ra, rb = _rankdata(a), _rankdata(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = math.sqrt(float(ra @ ra) * float(rb @ rb))
    return float(ra @ rb) / denom if denom else float("nan")


def _rankdata(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(x) + 1, dtype=np.float64)
    # average ties
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    return (sums / counts)[inv]


def orthogonal_procrustes(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Solve argmin_R ||X R - Y||_F over orthogonal R (R = U Vᵀ from SVD of XᵀY)."""
    U, _, Vt = np.linalg.svd(X.T @ Y, full_matrices=False)
    return U @ Vt


def roc_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """AUC via the Mann–Whitney U statistic (average-rank tie handling)."""
    ranks = _rankdata(scores)  # average ranks so tied scores contribute 0.5 each
    pos = labels == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return (ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


# ─────────────────────────────────────────────────────────────────────────────
#  commands
# ─────────────────────────────────────────────────────────────────────────────
def cmd_smoke(vvs: VVS, cfg: dict) -> None:
    _hr("§1 smoke test")
    health = vvs.healthz()
    print("healthz:", json.dumps(health, indent=2)[:400])
    arms = vvs.arms()
    print("arms:", json.dumps(arms)[:400])

    _hr("§2 dump — at-rest representation per arm")
    for arm in cfg["arms"]:
        try:
            recs = vvs.dump(arm, limit=1)
            kind = recs[0].get("representation", {}).get("kind") if recs else None
            print(f"  arm {arm}: kind={kind!r}")
        except requests.HTTPError as e:
            print(f"  arm {arm}: dump error {e.response.status_code}")

    _hr("§2 oracle — search scores per arm")
    q = vvs.embed("quarterly report")
    for arm in cfg["arms"]:
        try:
            res = vvs.oracle(arm, q, top_k=3)
            print(f"  arm {arm}: {[(r.get('doc_id'), round(r.get('score', 0), 4)) for r in res]}")
        except requests.HTTPError as e:
            print(f"  arm {arm}: oracle error {e.response.status_code}")


def cmd_kplus(vvs: VVS, cfg: dict) -> None:
    _hr("§3 chosen-plaintext (K+)")
    v = vvs.embed("the staging db password is PLANTED_SECRET")
    print(f"embed: dim={v.shape[0]}  head={np.round(v[:3], 5).tolist()}")

    arm = cfg["searchable_arm"]
    out = vvs.insert_chunk(arm, "attacker known-plaintext chunk")
    print(f"insert into arm {arm}: doc_id={out.get('doc_id')} "
          f"kind={out.get('representation', {}).get('kind')!r}")
    print("→ one known (plaintext, stored-vector) pair = the Procrustes input.")


def cmd_attack_a(vvs: VVS, cfg: dict, limit: int = 60) -> None:
    """Distance leakage: correlate each arm's stored-distance matrix against the
    plaintext-arm distances, aligned by doc_id (TESTING.md §4a)."""
    _hr("§4a distance leakage (dump)")
    ref_arm = cfg["plaintext_arm"]
    ref_ids, ref_mat = collect_vectors(vvs.dump(ref_arm, limit))
    if ref_mat is None:
        print(f"  plaintext arm {ref_arm} exposed no numeric vectors — cannot reference.")
        return
    ref_index = {d: i for i, d in enumerate(ref_ids)}
    ref_d = pairwise_distances(ref_mat)
    print(f"  reference = arm {ref_arm} (plaintext), {len(ref_ids)} docs")

    for arm in cfg["arms"]:
        if arm == ref_arm:
            continue
        ids, mat = collect_vectors(vvs.dump(arm, limit))
        if mat is None:
            why = "opaque bytes by design" if arm == cfg["strong_arm"] else "no numeric vector in representation"
            print(f"  arm {arm}: no distances ({why})")
            continue
        # align to the reference doc order
        common = [d for d in ids if d in ref_index]
        if len(common) < 3:
            print(f"  arm {arm}: too few aligned docs ({len(common)})")
            continue
        sel_ref = ref_mat[[ref_index[d] for d in common]]
        id_index = {d: i for i, d in enumerate(ids)}
        sel_arm = mat[[id_index[d] for d in common]]
        rho = spearman(pairwise_distances(sel_ref), pairwise_distances(sel_arm))
        verdict = "≈ plaintext (distance-preserving)" if rho > 0.99 else "partial leakage" if rho > 0.1 else "low"
        print(f"  arm {arm}: Spearman ρ = {rho:.4f}   {verdict}")


def cmd_attack_b(vvs: VVS, cfg: dict, n: int = 40) -> None:
    """Procrustes / known-plaintext against the searchable arm (TESTING.md §4b).

    Inserts n attacker chunks, collects (plaintext embedding, stored transform)
    pairs, fits an orthogonal map on a train split, and reports held-out fit.
    Full recovery needs n ≥ d (=%d); below that it is under-determined — the
    demo corpus can only show the trend.""" % cfg["dim"]
    _hr(f"§4b Procrustes / known-plaintext  (arm {cfg['searchable_arm']}, n={n}, d={cfg['dim']})")
    arm = cfg["searchable_arm"]
    X, Y = [], []
    for i in range(n):
        text = f"orf-procrustes-probe-{i:04d} lorem ipsum dolor sit amet {i*7919}"
        stored = extract_vector(vvs.insert_chunk(arm, text).get("representation"))
        if stored is None:
            print("  arm exposed no numeric transform on insert — cannot fit.")
            return
        X.append(vvs.embed(text))
        Y.append(stored)
    w = min(min(v.shape[0] for v in X), min(v.shape[0] for v in Y))
    X = np.vstack([v[:w] for v in X])
    Y = np.vstack([v[:w] for v in Y])

    split = max(2, int(n * 0.7))
    R = orthogonal_procrustes(X[:split], Y[:split])
    pred = X[split:] @ R
    resid = np.linalg.norm(pred - Y[split:]) / max(np.linalg.norm(Y[split:]), 1e-12)
    cos = float(np.mean(np.sum(pred * Y[split:], axis=1) /
                        (np.linalg.norm(pred, axis=1) * np.linalg.norm(Y[split:], axis=1) + 1e-12)))
    print(f"  held-out relative residual = {resid:.4f}   mean cosine = {cos:.4f}")
    print(f"  n/d = {n}/{cfg['dim']} = {n/cfg['dim']:.3f}  "
          f"({'over' if n >= cfg['dim'] else 'under'}-determined)")


def cmd_attack_c(vvs: VVS, cfg: dict, probe: str = "patient record note") -> None:
    """Oracle leak: same query to plaintext arm and strong arm; scores match to
    many significant figures (TESTING.md §4c)."""
    _hr("§4c oracle leak (plaintext arm vs strong arm)")
    a_arm, d_arm = cfg["plaintext_arm"], cfg["strong_arm"]
    q = vvs.embed(probe)
    top = 5
    ra = {r["doc_id"]: r["score"] for r in vvs.oracle(a_arm, q, top_k=top)}
    rd = {r["doc_id"]: r["score"] for r in vvs.oracle(d_arm, q, top_k=top)}
    common = [d for d in ra if d in rd]
    if not common:
        print("  no overlapping doc_ids between the two arms' results.")
        return
    max_abs = max(abs(ra[d] - rd[d]) for d in common)
    sig = -math.log10(max_abs) if max_abs > 0 else float("inf")
    print(f"  probe={probe!r}  compared {len(common)} shared docs")
    for d in common[:3]:
        print(f"    {d}: {a_arm}={ra[d]:.9f}  {d_arm}={rd[d]:.9f}  Δ={abs(ra[d]-rd[d]):.2e}")
    print(f"  max |Δ| = {max_abs:.2e}  (~{sig:.1f} significant figures agree)")


def cmd_attack_d(vvs: VVS, cfg: dict, k: int = 12) -> None:
    """Membership inference via the oracle plane (works for every arm incl. D).

    Positives = real in-corpus documents. We take their true embeddings from the
    plaintext-arm dump (already indexed), so no inserts are needed — which both
    avoids polluting the corpus and dodges the backend's ~6 docs/min indexing lag
    (freshly inserted chunks aren't searchable yet, so they can't be positives).
    Negatives = out-of-corpus texts embedded but never stored. Feature = top-1
    oracle score of each query; compute AUC (TESTING.md §4d).
    """
    arm = cfg["strong_arm"]
    _hr(f"§4d membership inference (arm {arm} via oracle, k={k})")
    ref_ids, ref_mat = collect_vectors(vvs.dump(cfg["plaintext_arm"], limit=max(60, k * 4)))
    if ref_mat is None:
        print(f"  plaintext arm {cfg['plaintext_arm']} exposed no vectors — cannot source in-corpus queries.")
        return
    kk = min(k, ref_mat.shape[0])
    scores, labels = [], []
    for i in range(kk):  # in-corpus positives: query with a real stored embedding
        res = vvs.oracle(arm, ref_mat[i], top_k=1)
        scores.append(res[0]["score"] if res else 0.0)
        labels.append(1)
    for i in range(kk):  # out-of-corpus negatives: never-stored text
        q = vvs.embed(f"orf-nonmember-{i:04d} never inserted {i*15485863}")
        res = vvs.oracle(arm, q, top_k=1)
        scores.append(res[0]["score"] if res else 0.0)
        labels.append(0)
    auc = roc_auc(np.asarray(scores), np.asarray(labels))
    pos_mean = np.mean([s for s, l in zip(scores, labels) if l == 1])
    neg_mean = np.mean([s for s, l in zip(scores, labels) if l == 0])
    print(f"  top-1 score  in-corpus mean={pos_mean:.4f}  out mean={neg_mean:.4f}  (n={kk}/side)")
    print(f"  membership AUC = {auc:.4f}  (0.5 = chance, 1.0 = perfect leakage)")


def cmd_boundary(vvs: VVS, cfg: dict) -> None:
    """What must NOT work (TESTING.md §5)."""
    _hr("§5 boundary — these must hold")
    ok = True
    for p in ("/keys", "/documents", "/corpus", "/openapi.json", "/docs", "/debug"):
        code = vvs.s.get(vvs.base + p, timeout=vvs.timeout).status_code
        good = code == 404
        ok &= good
        print(f"  {p} -> {code} {'✓' if good else '✗ (expected 404)'}")

    # a caller cannot address a corpus doc_id on insert
    r = vvs.s.post(vvs._url("chunks", arm=cfg["plaintext_arm"]),
                   json={"text": "x", "doc_id": "c2-00000"}, timeout=vvs.timeout)
    good = r.status_code == 422
    ok &= good
    print(f"  POST chunks with corpus doc_id -> {r.status_code} {'✓' if good else '✗ (expected 422)'}")

    # a planted secret never appears in a dump
    body = vvs.get("dump", params={"limit": 60}, arm=cfg["searchable_arm"]).text
    leaked = body.count("PLANTED_SECRET")
    good = leaked == 0
    ok &= good
    print(f"  planted secret 'PLANTED_SECRET' in dump -> {leaked} {'✓' if good else '✗ (leak!)'}")
    print(f"\n  boundary: {'ALL HOLD ✓' if ok else 'VIOLATION ✗'}")


def cmd_all(vvs: VVS, cfg: dict) -> None:
    cmd_smoke(vvs, cfg)
    cmd_kplus(vvs, cfg)
    cmd_attack_a(vvs, cfg)
    cmd_attack_c(vvs, cfg)
    cmd_attack_d(vvs, cfg)
    cmd_boundary(vvs, cfg)
    print("\n(skipped attack-b Procrustes — run it explicitly; it inserts many chunks.)")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Attack harness for the embedding-attack-lab boundary service.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Read-only except K+ inserts. Authorized targets only.")
    p.add_argument("--base-url", default=DEFAULTS["base_url"], help="service base URL")
    p.add_argument("--arms", default=None, help="comma list, e.g. A,B,C,D")
    p.add_argument("--dim", type=int, default=DEFAULTS["dim"], help="embedding dimension")
    p.add_argument("--timeout", type=float, default=DEFAULTS["timeout"])
    p.add_argument("--debug", action="store_true", help="log each HTTP request")

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="§1–2 health, arms, dump kinds, oracle")
    sub.add_parser("kplus", help="§3 chosen-plaintext embed + known-chunk insert")
    a = sub.add_parser("attack-a", help="§4a distance leakage (Spearman ρ)")
    a.add_argument("--limit", type=int, default=60)
    b = sub.add_parser("attack-b", help="§4b Procrustes / known-plaintext")
    b.add_argument("-n", type=int, default=40, help="known chunks to insert")
    c = sub.add_parser("attack-c", help="§4c oracle leak (plaintext vs strong)")
    c.add_argument("--probe", default="patient record note")
    d = sub.add_parser("attack-d", help="§4d membership inference (AUC)")
    d.add_argument("-k", type=int, default=12, help="positives/negatives each")
    sub.add_parser("boundary", help="§5 what must NOT work")
    sub.add_parser("all", help="everything except the heavy Procrustes")

    # keep the §/ρ/✓ glyphs from crashing a legacy-codepage console (e.g. cp950)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = p.parse_args(argv)

    cfg = dict(DEFAULTS)
    cfg["dim"] = args.dim
    if args.arms:
        cfg["arms"] = args.arms.split(",")

    vvs = VVS(args.base_url, args.timeout, debug=args.debug)
    print(f"target: {vvs.base}   arms: {','.join(cfg['arms'])}   dim: {cfg['dim']}")

    try:
        if args.cmd == "smoke":
            cmd_smoke(vvs, cfg)
        elif args.cmd == "kplus":
            cmd_kplus(vvs, cfg)
        elif args.cmd == "attack-a":
            cmd_attack_a(vvs, cfg, limit=args.limit)
        elif args.cmd == "attack-b":
            cmd_attack_b(vvs, cfg, n=args.n)
        elif args.cmd == "attack-c":
            cmd_attack_c(vvs, cfg, probe=args.probe)
        elif args.cmd == "attack-d":
            cmd_attack_d(vvs, cfg, k=args.k)
        elif args.cmd == "boundary":
            cmd_boundary(vvs, cfg)
        elif args.cmd == "all":
            cmd_all(vvs, cfg)
    except requests.ConnectionError as e:
        print(f"\nconnection error: {e}", file=sys.stderr)
        return 2
    except requests.HTTPError as e:
        print(f"\nHTTP {e.response.status_code} on {e.response.url}\n{e.response.text[:300]}",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
