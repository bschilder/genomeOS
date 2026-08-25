"""Is JAX actually using the GPU, and how much faster is it? (issue #104)

A GPU claim is worthless without the device list and a timed comparison in the log. This exists
because three pod runs were billed at GPU rates without either being recorded.

    python scripts/gpu_check.py
"""

from __future__ import annotations

import time

import numpy as np


def main() -> None:
    import jax
    import jax.numpy as jnp

    print("jax version    :", jax.__version__)
    print("JAX DEVICES    :", jax.devices())
    print("local devices  :", jax.local_device_count())
    print("default backend:", jax.default_backend())
    try:
        print("cpu devices    :", jax.devices("cpu"))
    except RuntimeError as error:
        print("cpu devices    : unavailable —", error)
    try:
        print("gpu devices    :", jax.devices("gpu"))
    except RuntimeError as error:
        print("gpu devices    : NONE —", error)

    # Cholesky of an M x M matrix is the inducing-point GP's inner loop, so benchmark that
    # rather than a generic matmul.
    rng = np.random.default_rng(0)
    for size in (800, 1500):
        base = rng.standard_normal((size, size)).astype("float32")
        matrix = base @ base.T + size * np.eye(size, dtype="float32")
        for backend in ("cpu", "gpu"):
            try:
                device = jax.devices(backend)[0]
            except RuntimeError:
                print(f"  M={size:5d} {backend:3s}: unavailable")
                continue
            placed = jax.device_put(jnp.asarray(matrix), device)
            jnp.linalg.cholesky(placed).block_until_ready()  # compile
            start = time.perf_counter()
            for _ in range(20):
                jnp.linalg.cholesky(placed).block_until_ready()
            print(f"  M={size:5d} {backend:3s}: {(time.perf_counter() - start) / 20 * 1000:7.2f} ms/cholesky")


if __name__ == "__main__":
    main()
