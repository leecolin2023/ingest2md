"""Golden-path ASR check: transcribe the model's own example audio.

If the fbank frontend were wrong, the CTC output would be garbage. Correct,
readable Chinese/English text is the strongest cheap evidence that the feature
frontend, the session adapter and the decoder are wired correctly together.

Requires the ``local-asr`` extra and the downloaded SenseVoiceSmall ONNX export.

Run from anywhere:  python tools/validate_asr.py
"""
from __future__ import annotations

import glob
import os
import time

from _paths import EXAMPLE_DIR, MODEL_DIR, require

try:
    import kaldi_native_fbank  # noqa: F401  (imported by funasr_onnx.frontend)
    from funasr_onnx import SenseVoiceSmall
except ImportError as exc:  # pragma: no cover - optional extra
    print(f"ASR stack not installed ({exc}): pip install -e '.[local-asr]'")
    raise SystemExit(2)

from ingest2md.transcription import funasr_onnx_compat

require(MODEL_DIR / "model.onnx", "SenseVoiceSmall ONNX export")
require(EXAMPLE_DIR, "SenseVoiceSmall example audio")

print("=" * 88)
print("Loading SenseVoiceSmall ONNX (quantize=False) via the native fbank frontend")
print("=" * 88)
t0 = time.time()
model = SenseVoiceSmall(str(MODEL_DIR), batch_size=1, quantize=False)
print(f"loaded in {time.time() - t0:.1f}s")
print(f"  frontend window      : {model.frontend.opts.frame_opts.window_type}")
print(f"  frontend samp_freq   : {model.frontend.opts.frame_opts.samp_freq}")
print(f"  frontend num_bins    : {model.frontend.opts.mel_opts.num_bins}")
print(f"  lfr_m / lfr_n        : {model.frontend.lfr_m} / {model.frontend.lfr_n}")
print(f"  cmvn_file            : {os.path.basename(str(model.frontend.cmvn_file))}")
print()
print("  ONNX session inputs  :", model.ort_infer.get_input_names())
print("  ONNX session outputs :", model.ort_infer.get_output_names())

# A single-output export needs the adapter; a two-output native FunASR export
# reports "not needed" and is left untouched.
status = funasr_onnx_compat.adapt_session(model.ort_infer.session)
print("  compat adapter       :", status)

print()
print("=" * 88)
print("Transcribing the model's own example audio")
print("=" * 88)
files = sorted(glob.glob(os.path.join(str(EXAMPLE_DIR), "*.mp3")))
if not files:
    print(f"  no example audio in {EXAMPLE_DIR}")
    raise SystemExit(1)

rc = 0
for path in files:
    t = time.time()
    try:
        out = model(path, language="auto", textnorm="withitn")
        text = out[0] if isinstance(out, (list, tuple)) and out else out
        print(f"  {os.path.basename(path):<12} ({time.time() - t:5.1f}s)")
        print(f"      {text}")
    except Exception as exc:
        rc = 1
        print(f"  {os.path.basename(path):<12} FAILED {type(exc).__name__}: {exc}")

print()
print("=" * 88)
print("RESULT:", "transcription produced output" if rc == 0 else "FAILURES ABOVE")
print("=" * 88)
raise SystemExit(rc)
