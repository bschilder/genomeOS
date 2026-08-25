"""Launch a high-resolution surface fit on a Runpod GPU (design §7, §5; issue #104).

The HSGP basis grows as m^3 on the sphere, so the resolution that P2 actually needs is out of
reach on a laptop: m=6 resolves no feature finer than ~3,200 km, and India's tribal-belt
structure needs ~800 km, i.e. m≈24 and ~14,000 basis coefficients. The fits are pure offline
batch work (§5) and are embarrassingly parallel across variants, which is exactly the shape a
GPU pod serves well.

    python scripts/runpod_fit.py --plan                 # show what would be launched, cost first
    python scripts/runpod_fit.py --launch --hsgp-m 20

Nothing here runs on the serving path.
"""

from __future__ import annotations

import argparse
import json
import os
import textwrap
import urllib.error
import urllib.request

API = "https://rest.runpod.io/v1"

#: Datacenters in rough order of proximity to New York, per repo convention. Latency matters
#: for interactive debugging and for pulling artifacts back; EU/APAC are avoided deliberately.
#: Ordered by rough proximity to New York, and verified against what `POST /v1/pods` actually
#: accepts rather than from memory or from `list-data-centers`. Two traps:
#:   * US-NY-1, US-NJ-1, US-PA-2, US-OH-2, US-VA-1 and US-OR-1 do not exist at all.
#:   * The v2 datacenter listing is a superset of the v1 pod enum — US-MO-1, US-MO-2, US-NE-1,
#:     US-CO-1, US-NC-2, US-WA-2 and CA-MTL-4 are listed there but rejected here.
#: The API validates the whole array, so one stale id fails the entire request.
PREFERRED_DATACENTERS: tuple[str, ...] = (
    "US-DE-1", "US-MD-1", "US-NC-1", "US-GA-1", "US-GA-2",
    "CA-MTL-1", "CA-MTL-2", "CA-MTL-3",
    "US-IL-1", "US-KS-2", "US-KS-3",
    "US-TX-1", "US-TX-3", "US-TX-4",
    "US-CA-2", "US-WA-1",
)

#: FP32 is what matters: PyTensor is float64 but JAX x64 is off, so the compiled NUTS kernel
#: runs single-precision. That rules out paying for FP64-heavy silicon. Ordered cheapest-first
#: among cards with enough VRAM — this model is tiny (m=24 is ~95 MB of basis matrix), so VRAM
#: is not the binding constraint and a big card would be wasted money.
GPU_PREFERENCE: tuple[tuple[str, float], ...] = (
    ("NVIDIA A40", 0.44),
    ("NVIDIA L40", 0.69),
    ("NVIDIA RTX 6000 Ada Generation", 0.74),
    ("NVIDIA L40S", 0.79),
    ("NVIDIA A100-SXM4-80GB", 1.59),
)

IMAGE = "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"


JOB_COMMANDS = {
    # Cheap and decisive: prints the device list and times the inducing GP's inner loop on each
    # backend. Run this before believing any GPU claim.
    "gpucheck": "run python scripts/gpu_check.py",
    "fit": (
        "run python scripts/plot_surface.py "
        "--observations /workspace/data/map_hbs_surveys.csv "
        "--out /workspace/out/hbs_surface_{approximation}.png "
        "--approximation {approximation} --n-inducing {n_inducing} --hsgp-m {hsgp_m} "
        "--draws {draws} --contraction-threshold 0.5"
    ),
    # Both, in one pod: the validation numbers and the figure they describe should come from the
    # same code at the same M, and a second pod launch is a second chance to forget to stop one.
    # Figure FIRST, validation second. A watchdog or a capacity loss truncates the tail, so the
    # single-fit deliverable must not be at the end: the one job that was ordered the other way
    # was killed at 50 minutes having written nothing, because validation only saves at the end.
    "validate+fit": (
        "echo '--- figure (1 fit) ---'; date; "
        "run python scripts/plot_surface.py "
        "--observations /workspace/data/map_hbs_surveys.csv "
        "--out /workspace/out/hbs_surface_geodesic.png "
        "--approximation inducing --n-inducing {n_inducing} --hsgp-m {hsgp_m} "
        "--draws {draws} --contraction-threshold 0.5 ; "
        "echo '--- figure done ---'; date; "
        "echo '--- validation ({n_folds} folds x 2 strategies) ---'; "
        "run python scripts/validate_holdout.py "
        "--observations /workspace/data/map_hbs_surveys.csv "
        "--out /workspace/out --n-folds {n_folds} "
        "--n-inducing {n_inducing_fold} --draws {draws} ; "
        "echo '--- validation done ---'; date"
    ),
    "validate": (
        "run python scripts/validate_holdout.py "
        "--observations /workspace/data/map_hbs_surveys.csv "
        "--out /workspace/out --n-folds {n_folds} "
        "--n-inducing {n_inducing} --draws {draws}"
    ),
}


def entrypoint(args) -> str:
    """Pod start command.

    Deliberately no `set -x`: it echoes expanded variables, and this script sees a GitHub token.
    Progress is marked with explicit echo lines instead.
    """
    # Folds train on (k-1)/k of the data, so the per-fold inducing budget must be smaller to
    # stay under fit_surface's M<<N guard.
    n_inducing_fold = int(args.n_inducing * (args.n_folds - 1) / args.n_folds)
    job_command = JOB_COMMANDS[args.job].format(
        approximation=args.approximation,
        n_inducing=args.n_inducing,
        n_inducing_fold=n_inducing_fold,
        hsgp_m=args.hsgp_m,
        draws=args.draws,
        n_folds=args.n_folds,
    )
    return textwrap.dedent(f"""
        set -uo pipefail
        # NOT `set -e` around the whole script. Under it, any failure exits the container, Runpod
        # restarts it, and the entrypoint re-clones and re-fails on a loop — billing the entire
        # time. One such loop ran 4.3 hours unnoticed. Failures are trapped and the pod is held
        # open instead, so the error can be read and the pod stopped deliberately.
        hold() {{
            echo "===== HELD (exit ${{1:-0}}) — pod is idle; stop it when done ====="
            sleep infinity
        }}
        run() {{ "$@" || {{ echo "!!!!! FAILED: $* (exit $?)"; hold $?; }}; }}
        echo "===== ENV ====="
        nvidia-smi || echo "no GPU visible"
        if [[ -n "${{BSCHILDER_GITHUB2:-}}" ]]; then
            echo "  BSCHILDER_GITHUB2 present? YES"
        else
            echo "  BSCHILDER_GITHUB2 present? NO"
        fi

        echo "===== CLONE ====="
        git config --global url."https://x-access-token:${{BSCHILDER_GITHUB2}}@github.com/".insteadOf "https://github.com/"
        chmod 600 /root/.gitconfig
        # /workspace is a persistent volume, so a restarted pod finds the clone already there and
        # `git clone` fails the whole entrypoint under `set -e`. Make it idempotent.
        rm -rf /workspace/genomeOS
        run git clone --depth 1 --branch {args.ref} https://github.com/bschilder/genomeOS /workspace/genomeOS
        cd /workspace/genomeOS || hold 1

        echo "===== INSTALL ====="
        run pip install --no-cache-dir -e '.[atlas,surfaces,geo,figures]'
        # CUDA-enabled JAX. numpyro picks the device up automatically; no model change needed.
        run pip install --no-cache-dir --upgrade "jax[cuda12]"
        # Recorded explicitly: a GPU claim is worthless unless the device list is in the log.
        run python -c "import jax; print('JAX DEVICES:', jax.devices())"

        echo "===== FETCH DATA ====="
        run python scripts/fetch_map_hbs.py --layer hbs --out /workspace/data/map_hbs_surveys.csv

        echo "===== {args.job} ====="
        {job_command}

        echo "===== DONE ====="
        ls -la /workspace/out
        sleep infinity
    """).strip()


def _request(path: str, payload: dict | None = None) -> dict:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise SystemExit("RUNPOD_API_KEY is not set")
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def plan(args) -> dict:
    gpu_ids = [gpu for gpu, _ in GPU_PREFERENCE]
    return {
        "name": f"genomeos-hbs-{args.job}",
        "imageName": IMAGE,
        "gpuTypeIds": gpu_ids,
        "gpuCount": 1,
        # Two-phase: preferred US/CA datacenters first. Only fall back to "anywhere" when every
        # US/CA pairing is out of capacity, per repo convention.
        "dataCenterIds": list(PREFERRED_DATACENTERS),
        "containerDiskInGb": 40,
        "volumeInGb": 20,
        "volumeMountPath": "/workspace",
        "ports": ["22/tcp"],
        "env": {
            # Account-level secrets are not auto-injected; they must be referenced explicitly.
            "BSCHILDER_GITHUB2": "{{ RUNPOD_SECRET_BSCHILDER_GITHUB2 }}",
        },
        "dockerStartCmd": ["bash", "-lc", entrypoint(args)],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", choices=tuple(JOB_COMMANDS), default="fit")
    ap.add_argument("--n-folds", type=int, default=5)
    ap.add_argument("--approximation", choices=("hsgp", "inducing"), default="inducing")
    ap.add_argument("--n-inducing", type=int, default=400,
                    help="inducing points; the M^3 Cholesky per leapfrog step is the GPU work")
    ap.add_argument("--hsgp-m", type=int, default=12, help="HSGP basis functions per dimension")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--ref", default="main", help="git ref to fit from")
    ap.add_argument("--launch", action="store_true", help="actually create the pod")
    ap.add_argument("--plan", action="store_true", help="print the request and exit")
    args = ap.parse_args()

    spec = plan(args)
    cheapest = min(price for _, price in GPU_PREFERENCE)
    dearest = max(price for _, price in GPU_PREFERENCE)
    if args.approximation == "inducing":
        print(f"inducing points: {args.n_inducing:,}  (resolution follows data density)")
    else:
        print(
            f"basis functions: {args.hsgp_m ** 3:,}  "
            f"(finest feature ~{2 * 1.5 / args.hsgp_m * 6371:.0f} km, everywhere)"
        )
    print(f"gpu candidates : {', '.join(g for g, _ in GPU_PREFERENCE)}")
    print(f"datacenters    : {', '.join(PREFERRED_DATACENTERS[:6])}, …")
    print(f"cost           : ${cheapest:.2f}–${dearest:.2f}/hr — the pod bills until it is stopped")

    if args.plan or not args.launch:
        print("\n--- request body ---")
        print(json.dumps({k: v for k, v in spec.items() if k != "dockerStartCmd"}, indent=2))
        print("\n(pass --launch to create it)")
        return

    try:
        pod = _request("/pods", spec)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"launch failed: {error.code} {error.read().decode()[:400]}") from error
    print(f"\nlaunched pod {pod.get('id')} — stop it when the fit is retrieved, it bills hourly")


if __name__ == "__main__":
    main()
