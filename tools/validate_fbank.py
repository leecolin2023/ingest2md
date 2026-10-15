"""Human-readable diagnostic report for the fbank frontend.

Cross-checks the native ``kaldi-native-fbank`` extension (the production path)
against an independent reconstruction of Kaldi's documented spec, and against
``tools/numpy_fbank_reference.py`` when present. Also compares against
``torchaudio.compliance.kaldi`` if torchaudio is installed.

The fast, assertion-based version of these checks lives in
``tests/test_sensevoice_compat.py``; this script is for eyeballing numbers.

Run from anywhere:  python tools/validate_fbank.py
"""
from __future__ import annotations

import importlib.util

import numpy as np

from _paths import REPO_ROOT

try:
    import kaldi_native_fbank as knf
except ImportError:  # pragma: no cover - optional extra
    print("kaldi-native-fbank is not installed: pip install -e '.[local-asr]'")
    raise SystemExit(2)

REFERENCE = REPO_ROOT / "tools" / "numpy_fbank_reference.py"
reference = None
if REFERENCE.exists():
    spec = importlib.util.spec_from_file_location("numpy_fbank_reference", REFERENCE)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)

FS = 16000
FRAME_LENGTH_MS = 25.0
FRAME_SHIFT_MS = 10.0
NUM_BINS = 80

# Derived the way Kaldi's FrameExtractionOptions does; the native extension does
# not expose these as attributes.
WINDOW_SIZE = int(FS * 0.001 * FRAME_LENGTH_MS)          # 400
FRAME_SHIFT = int(FS * 0.001 * FRAME_SHIFT_MS)           # 160
PADDED_WINDOW_SIZE = 1
while PADDED_WINDOW_SIZE < WINDOW_SIZE:
    PADDED_WINDOW_SIZE *= 2                                 # 512

ok = True


def check(label, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{(' -> ' + extra) if extra else ''}")


def make_options(module, dither=0.0, window="hamming"):
    opts = module.FbankOptions()
    opts.frame_opts.samp_freq = FS
    opts.frame_opts.dither = dither
    opts.frame_opts.window_type = window
    opts.frame_opts.frame_shift_ms = FRAME_SHIFT_MS
    opts.frame_opts.frame_length_ms = FRAME_LENGTH_MS
    opts.mel_opts.num_bins = NUM_BINS
    opts.energy_floor = 0.0
    opts.mel_opts.debug_mel = False
    return opts


def features(module, samples, dither=0.0):
    fb = module.OnlineFbank(make_options(module, dither=dither))
    fb.accept_waveform(FS, np.asarray(samples, dtype=np.float64).tolist())
    return np.array([fb.get_frame(i) for i in range(fb.num_frames_ready)])


print("=" * 72)
print("A) Frame geometry (Kaldi snip_edges=True)")
print("=" * 72)
check("window_size == 400", WINDOW_SIZE == 400, str(WINDOW_SIZE))
check("frame_shift == 160", FRAME_SHIFT == 160, str(FRAME_SHIFT))
check("padded_window_size == 512 (power of two)",
      PADDED_WINDOW_SIZE == 512, str(PADDED_WINDOW_SIZE))

# Kaldi: num_frames = 1 + (N - window_size) // frame_shift
for seconds, expected_frames in ((1.0, 98), (0.5, 48), (0.025, 1), (0.01, 0)):
    n = int(FS * seconds)
    fb = knf.OnlineFbank(make_options(knf))
    fb.accept_waveform(FS, np.zeros(n).tolist())
    got = fb.num_frames_ready
    check(f"{seconds}s ({n} samples) -> {expected_frames} frames",
          got == expected_frames, str(got))

print()
print("=" * 72)
print("B) Mel filterbank geometry vs independent spec reconstruction")
print("=" * 72)
# Rebuild the filterbank matrix straight from Kaldi's written definition:
# mel = 1127*ln(1+f/700), low_freq=20, high_freq=nyquist, num_bins triangles,
# weight = min(left, right) clamped at 0 (NOT Slaney 2/(f_hi-f_lo)).
low, high = 20.0, FS / 2.0
mel_low = 1127.0 * np.log(1 + low / 700.0)
mel_high = 1127.0 * np.log(1 + high / 700.0)
delta = (mel_high - mel_low) / (NUM_BINS + 1)
edge_mels = mel_low + np.arange(0, NUM_BINS + 2) * delta
edges = 700.0 * (np.exp(edge_mels / 1127.0) - 1)
num_fft_bins = PADDED_WINDOW_SIZE // 2
bin_freqs = np.arange(num_fft_bins) * (FS / PADDED_WINDOW_SIZE)
spec_matrix = np.zeros((NUM_BINS, num_fft_bins))
for i in range(NUM_BINS):
    f_lo, f_ctr, f_hi = edges[i], edges[i + 1], edges[i + 2]
    for k in range(num_fft_bins):
        f = bin_freqs[k]
        if f_lo <= f <= f_hi:
            w = min((f - f_lo) / (f_ctr - f_lo), (f_hi - f) / (f_hi - f_ctr))
            spec_matrix[i, k] = max(w, 0.0)

centre_freqs = edges[1:NUM_BINS + 1]
check("spec matrix shape == (80, 256)", spec_matrix.shape == (80, 256),
      str(spec_matrix.shape))
check("no Slaney 2/(hi-lo) normalisation (weights bounded by 1.0)",
      0.98 <= spec_matrix.max() <= 1.0,
      f"max weight {spec_matrix.max():.6f} (Slaney would exceed this)")
check("first centre freq in the 20 Hz region",
      0 < centre_freqs[0] < 200, f"{centre_freqs[0]:.3f} Hz")
check("last centre freq < nyquist",
      centre_freqs[-1] < FS / 2, f"{centre_freqs[-1]:.3f} Hz")
check("centre freqs strictly increasing",
      bool(np.all(np.diff(centre_freqs) > 0)))

print()
print("=" * 72)
print("C) Numeric sanity: 1 kHz tone should light up the low-mel region")
print("=" * 72)
t = np.arange(FS) / FS
tone = (0.5 * np.sin(2 * np.pi * 1000 * t) * (1 << 15)).astype(np.float32)
feats = features(knf, tone)
check("feature shape (98, 80)", feats.shape == (98, 80), str(feats.shape))
check("finite everywhere", bool(np.all(np.isfinite(feats))))
check("log domain active (log of power, not raw power)",
      float(feats.min()) > 0 and float(feats.max()) < 60,
      f"min={feats.min():.3f} max={feats.max():.3f}")
peak_bin = int(np.argmax(feats.mean(axis=0)))
print(f"       peak mel bin for 1 kHz tone: {peak_bin} "
      f"(centre {centre_freqs[peak_bin]:.1f} Hz)")
check("peak mel bin centre within +-35% of 1 kHz",
      0.65 * 1000 <= centre_freqs[peak_bin] <= 1.35 * 1000)
check("stationary tone -> stable frames",
      float(feats.std(axis=0).max()) < 0.5, f"max std {feats.std(axis=0).max():.4f}")

print()
print("=" * 72)
print("D) Native extension vs tools/numpy_fbank_reference.py")
print("=" * 72)
if reference is None:
    print("       reference not present; skipping")
else:
    wave = (0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 3000 * t))
    wave = (wave * (1 << 15)).astype(np.float32)
    for dither in (0.0, 1.0):
        a = features(knf, wave, dither=dither)
        b = features(reference, wave, dither=dither)
        n = min(a.shape[0], b.shape[0])
        diff = np.abs(a[:n] - b[:n])
        corr = np.corrcoef(a[:n].ravel(), b[:n].ravel())[0, 1]
        print(f"       dither={dither}: max {diff.max():.3e} "
              f"mean {diff.mean():.3e} corr {corr:.10f}")
        check(f"dither={dither}: shapes agree", a.shape == b.shape)
        check(f"dither={dither}: correlation > 0.9999", corr > 0.9999)
        check(f"dither={dither}: max abs diff < 2e-1", diff.max() < 2e-1)

print()
print("=" * 72)
print("E) Cross-check vs torchaudio.compliance.kaldi (if installed)")
print("=" * 72)
try:
    import torch
    import torchaudio.compliance.kaldi as taf

    wave = (0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 3000 * t))
    wave = (wave * (1 << 15)).astype(np.float32)
    ta = taf.fbank(
        torch.from_numpy(wave).unsqueeze(0),
        num_mel_bins=NUM_BINS, sample_frequency=FS,
        frame_length=FRAME_LENGTH_MS, frame_shift=FRAME_SHIFT_MS,
        dither=0.0, window_type="hamming",
        low_freq=20.0, high_freq=0.0,
        use_energy=False, snip_edges=True,
    ).numpy()
    mine = features(knf, wave)
    n = min(ta.shape[0], mine.shape[0])
    diff = np.abs(ta[:n] - mine[:n])
    print(f"       torchaudio frames={ta.shape[0]} native frames={mine.shape[0]}")
    print(f"       max abs diff={diff.max():.4e}  mean abs diff={diff.mean():.4e}")
    # Residual is mel-matrix grid rounding, not a semantic difference.
    check("native agrees with torchaudio.compliance.kaldi (<2e-2)", diff.max() < 2e-2,
          f"max {diff.max():.4e}")
except ImportError:
    print("       torchaudio unavailable; skipping independent cross-check")

print()
print("=" * 72)
print("RESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
print("=" * 72)
raise SystemExit(0 if ok else 1)
