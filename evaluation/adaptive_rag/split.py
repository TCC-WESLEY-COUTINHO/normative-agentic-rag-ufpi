"""Fixed DEV/TEST split of the exploratory questions; uses only dataset metadata."""

import random

SEED = 20261109
DEV_PER_STRATUM = {
    ("graduacao", "multi"): 3,
    ("graduacao", "single"): 3,
    ("pos_graduacao", "multi"): 3,
    ("pos_graduacao", "single"): 3,
}


def stratum(key):
    return (key.sector, "multi" if len(key.evidence) > 1 else "single")


def split(keys, *, seed=SEED):
    groups = {}
    for key in sorted(keys, key=lambda k: k.qid):
        groups.setdefault(stratum(key), []).append(key.qid)
    rng = random.Random(seed)
    dev = []
    for name in sorted(groups):
        members = groups[name]
        dev.extend(rng.sample(members, min(DEV_PER_STRATUM.get(name, 0), len(members))))
    dev = sorted(dev)
    return dict(
        seed=seed,
        strata={"/".join(k): len(v) for k, v in sorted(groups.items())},
        DEV=dev,
        TEST=sorted(k.qid for k in keys if k.qid not in dev),
    )
