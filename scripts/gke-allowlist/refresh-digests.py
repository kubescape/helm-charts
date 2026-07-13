#!/usr/bin/env python3
"""Refresh containerImageDigests in approved GKE Autopilot allowlists.

`containerImageDigests` is the ONLY mutable field of an approved WorkloadAllowlist,
so when a new node-agent version ships you just append its SHA-256 digest to the
existing file (no new allowlist version). This script automates that.

It covers both registries:
  - quay.io/kubescape/node-agent
  - quay.io/armosec/node-agent

For each allowlist file it finds every `containerImageDigests[].imageDigests` block,
infers which registry the block tracks from its existing `# quay.io/<reg>/node-agent:vX`
comments, fetches the latest release digests for that registry (skopeo), and reports
any that are missing. With --apply it inserts the missing entries (newest first) at the
top of the block, preserving the file's comment+digest format.

Usage:
  refresh-digests.py [--apply] [--max N] [FILE ...]
Default FILEs are the three 1.40 allowlists. Dry-run by default (prints a report).
Exit code: 0 = up to date, 10 = missing digests found (dry-run), 0 after --apply.
"""
import argparse, glob, os, re, shutil, subprocess, sys, json
from functools import lru_cache

# Repo root of the ARMO allowlist checkout. Override with $GKE_ALLOWLIST_REPO; falls back to the
# path used during development. If it doesn't exist, we fail loudly (see main) rather than silently
# scanning nothing.
REPO = os.environ.get(
    "GKE_ALLOWLIST_REPO",
    os.path.expanduser("~/projects/workspace-gke-autopilot-approval/gke-allow-list/ARMO"),
)
DEFAULT_FILES = sorted(glob.glob(f"{REPO}/*/1.40/*-1.40.yaml"))
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
REG_RE = re.compile(r"quay\.io/(armosec|kubescape)/node-agent")


def _skopeo(*args):
    if shutil.which("skopeo") is None:
        sys.exit("error: skopeo is not installed (needed to resolve image digests).")
    return subprocess.run(["skopeo", *args], capture_output=True, text=True, timeout=120)


@lru_cache(maxsize=None)
def latest(registry, maxn):
    """Return list of (tag, digest) for the latest `maxn` vX.Y.Z tags, newest first."""
    repo = f"quay.io/{registry}/node-agent"
    tags = _skopeo("list-tags", f"docker://{repo}")
    if tags.returncode != 0:
        sys.exit(f"skopeo list-tags failed for {repo}:\n{tags.stderr}")
    all_tags = [t for t in json.loads(tags.stdout)["Tags"] if TAG_RE.match(t)]
    all_tags.sort(key=lambda t: [int(x) for x in t[1:].split(".")], reverse=True)
    out = []
    for t in all_tags[:maxn]:
        ins = _skopeo("inspect", f"docker://{repo}:{t}")
        if ins.returncode == 0:
            d = json.loads(ins.stdout).get("Digest", "").replace("sha256:", "")
            if d:
                out.append((t, d))
    return out


def process(path, maxn, apply):
    lines = open(path).read().splitlines()
    # find each "imageDigests:" line and the extent of its block
    blocks = []  # (insert_after_idx, end_idx, registry, existing_digests:set)
    i = 0
    while i < len(lines):
        if re.match(r"^\s*imageDigests:\s*$", lines[i]):
            indent = len(lines[i]) - len(lines[i].lstrip())
            j = i + 1
            existing, reg = set(), None
            while j < len(lines):
                ln = lines[j]
                # block ends when indentation drops to <= the imageDigests indent on a non-blank, non-deeper line
                if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
                    break
                m = re.match(r"\s*-\s+([0-9a-f]{64})\s*$", ln)
                if m:
                    existing.add(m.group(1))
                rm = REG_RE.search(ln)
                if rm and reg is None:
                    reg = rm.group(1)
                j += 1
            blocks.append([i, j, reg, existing])
            i = j
        else:
            i += 1

    report, additions = [], []  # additions: (insert_idx, [new lines])
    for insert_after, _end, reg, existing in blocks:
        if not reg:
            report.append(f"  ! could not infer registry for block at line {insert_after+1}; skipping")
            continue
        latest_list = latest(reg, maxn)
        missing = [(t, d) for (t, d) in latest_list if d not in existing]
        report.append(f"  block@L{insert_after+1} [{reg}/node-agent]: "
                      f"{len(existing)} present, {len(missing)} new")
        for t, d in missing:
            report.append(f"      + {t}  sha256:{d[:16]}…")
        if missing:
            # build new lines (newest first), matched to the block's digest indentation
            digit_indent = " " * (len(lines[insert_after]) - len(lines[insert_after].lstrip()) + 2)
            new = []
            for t, d in missing:  # latest() is newest-first already
                new.append(f"{digit_indent}# quay.io/{reg}/node-agent:{t}")
                new.append(f"{digit_indent}- {d}")
            additions.append((insert_after + 1, new))

    total_new = sum(len(n)//2 for _, n in additions)
    print(f"\n{os.path.relpath(path)}")
    for r in report:
        print(r)

    if apply and additions:
        # apply bottom-up so earlier insert indices stay valid
        for idx, new in sorted(additions, key=lambda x: -x[0]):
            lines[idx:idx] = new
        open(path, "w").write("\n".join(lines) + "\n")
        print(f"  -> applied: inserted {total_new} digest(s)")
    return total_new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", default=DEFAULT_FILES)
    ap.add_argument("--apply", action="store_true", help="write changes in place")
    ap.add_argument("--max", type=int, default=20, help="latest N release tags per registry")
    args = ap.parse_args()
    files = args.files or DEFAULT_FILES
    if not files:
        sys.exit(f"error: no allowlist files given and none found under {REPO} "
                 f"(set $GKE_ALLOWLIST_REPO or pass file paths).")
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        sys.exit("error: allowlist file(s) not found: " + ", ".join(missing))
    total = sum(process(f, args.max, args.apply) for f in files)
    print(f"\nTotal new digests {'applied' if args.apply else 'available'}: {total}")
    if total and not args.apply:
        print("Re-run with --apply to insert them, then commit + push to Gerrit refs/for/main.")
        sys.exit(10)


if __name__ == "__main__":
    main()
