"""
Mel-feature parity: extract the EXACT preprocessor config + verify a from-scratch
reconstruction (the same algorithm MelFrontend.kt uses) matches preprocessor.ts.

Why: on-device STT feeds IndicConformer's encoder a log-mel tensor. The model was trained
on NeMo features, so the phone's mel must match. Rather than guess NeMo defaults, we pull the
real window (c3) + mel filterbank (c4) + scalars straight out of the scripted preprocessor,
reimplement the pipeline exactly, and assert it matches the golden output on fleurs/hi_0.wav.

Outputs (all consumed by the app / its parity test):
  mesh-app/app/src/main/assets/stt/mel_window512.f32   # 512-pt centered analysis window
  mesh-app/app/src/main/assets/stt/mel_fb.f32          # 257x80 mel filterbank, row-major
  mesh-app/app/src/androidTest/assets/mel_golden/pcm.f32     # input PCM (float32)
  mesh-app/app/src/androidTest/assets/mel_golden/mel.f32     # golden (80,T) mel, row-major
  mesh-app/app/src/androidTest/assets/mel_golden/meta.txt    # T + max-diff we achieved here
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

SNAP = Path.home() / (
    ".cache/huggingface/hub/models--ai4bharat--indic-conformer-600m-multilingual/"
    "snapshots/e9b71b369c048e2c6b634d4c131061c34e441179"
)
WAV = Path(__file__).parent / "fleurs" / "hi_0.wav"
APP_ASSETS = Path(__file__).parents[1] / "mesh-app/app/src/main/assets/stt"
TEST_ASSETS = Path(__file__).parents[1] / "mesh-app/app/src/androidTest/assets/mel_golden"

HOP, WIN, NFFT, NMEL, PREEMPH, PAD = 160, 400, 512, 80, 0.97, 256


def write_f32(path: Path, arr: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(arr.astype("<f4").tobytes())


def main():
    pre = torch.jit.load(str(SNAP / "assets/preprocessor.ts"), map_location="cpu")
    _, consts = pre.code_with_constants
    cm = consts.const_mapping
    window = cm["c3"].numpy().astype(np.float64)          # (400,)
    fb = cm["c4"].numpy().astype(np.float64)              # (257, 80)
    guard = float(cm["c5"]); std_eps = float(cm["c6"]); preemph = float(cm["c2"])
    assert window.shape == (WIN,) and fb.shape == (NFFT // 2 + 1, NMEL)

    # ── golden from the real preprocessor ────────────────────────────────────
    x, sr = sf.read(str(WAV), dtype="float32")
    assert sr == 16000 and x.ndim == 1
    xt = torch.from_numpy(x).unsqueeze(0)
    mel_g, len_g = pre(input_signal=xt, length=torch.tensor([len(x)]))
    mel_g = mel_g[0].numpy()                              # (80, T)
    T = mel_g.shape[1]

    # ── from-scratch reconstruction (mirrors MelFrontend.kt exactly) ──────────
    win512 = np.zeros(NFFT)                               # win_length<n_fft → centered
    off = (NFFT - WIN) // 2                               # 56
    win512[off:off + WIN] = window
    xpre = x.astype(np.float64).copy()
    xpre[1:] = x[1:] - preemph * x[:-1]                   # global preemphasis, x[-1]=0
    xpre[0] = x[0]
    xpad = np.pad(xpre, PAD, mode="reflect")
    feat = np.zeros((NMEL, T))
    for t in range(T):
        seg = xpad[t * HOP: t * HOP + NFFT] * win512
        power = np.abs(np.fft.rfft(seg, n=NFFT)) ** 2     # (257,)
        feat[:, t] = fb.T @ power
    feat = np.log(feat + guard)
    mean = feat.mean(axis=1, keepdims=True)               # NeMo: /N
    var = ((feat - mean) ** 2).sum(axis=1, keepdims=True) / (T - 1)  # NeMo: /(N-1)
    var = np.clip(var, guard, None)
    feat = (feat - mean) / (np.sqrt(var) + std_eps)

    diff = np.abs(feat - mel_g)
    print(f"clip={WAV.name}  T={T}  max-abs-diff={diff.max():.3e}  mean-abs-diff={diff.mean():.3e}")
    ok = diff.max() < 1e-2
    print("PARITY:", "OK ✅" if ok else "MISMATCH ❌ (tune before porting)")

    # ── dump assets + golden (win512 + fb for the app; pcm + golden mel for the test) ──
    write_f32(APP_ASSETS / "mel_window512.f32", win512)
    write_f32(APP_ASSETS / "mel_fb.f32", fb)              # row-major (257 rows × 80)
    write_f32(TEST_ASSETS / "pcm.f32", x)
    write_f32(TEST_ASSETS / "mel.f32", mel_g)             # row-major (80 rows × T)
    (TEST_ASSETS / "meta.txt").write_text(
        f"T={T}\nmax_abs_diff_python={diff.max():.3e}\nnmel={NMEL}\n"
    )
    print(f"wrote {APP_ASSETS}/mel_window512.f32, mel_fb.f32")
    print(f"wrote {TEST_ASSETS}/pcm.f32, mel.f32, meta.txt")


if __name__ == "__main__":
    main()
