from __future__ import annotations

import math

import numpy as np


def pack_f32(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def unpack_f32(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32, copy=False)
    b = b.astype(np.float32, copy=False)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    matrix = matrix.astype(np.float32, copy=False)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def normalize_vec(vec: np.ndarray) -> np.ndarray:
    vec = vec.astype(np.float32, copy=False)
    n = float(np.linalg.norm(vec))
    if n == 0.0 or math.isnan(n):
        return vec
    return vec / n

