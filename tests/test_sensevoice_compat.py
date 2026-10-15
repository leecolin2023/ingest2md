"""Tests for the SenseVoice ONNX compatibility layer.

Two independent pieces:

* ``ingest2md.transcription.funasr_onnx_compat`` -- adapts single-output
  SenseVoice ONNX exports for ``funasr_onnx``.
* the fbank frontend -- production uses the native ``kaldi-native-fbank`` wheel.
  ``tools/numpy_fbank_reference.py`` is a pure-NumPy reference kept for
  environments without that wheel, and is checked against the native extension
  when both are importable.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

# The ASR stack is an optional extra (`.[local-asr]`); CI installs only
# `.[test]`. Skip the whole module cleanly instead of erroring at collection.
knf = pytest.importorskip(
    "kaldi_native_fbank", reason="local-asr extra not installed"
)

from ingest2md.transcription import funasr_onnx_compat as compat

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tools" / "numpy_fbank_reference.py"


def _load_reference():
    spec = importlib.util.spec_from_file_location("numpy_fbank_reference", REFERENCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _options(module, dither=0.0, window="hamming", bins=80):
    opts = module.FbankOptions()
    opts.frame_opts.samp_freq = 16000
    opts.frame_opts.dither = dither
    opts.frame_opts.window_type = window
    opts.frame_opts.frame_shift_ms = 10.0
    opts.frame_opts.frame_length_ms = 25.0
    opts.mel_opts.num_bins = bins
    return opts


def _features(module, samples, dither=0.0):
    fb = module.OnlineFbank(_options(module, dither=dither))
    fb.accept_waveform(16000, np.asarray(samples, dtype=np.float64).tolist())
    return np.array([fb.get_frame(i) for i in range(fb.num_frames_ready)])


# ------------------------------------------------------------------ frontend
def test_native_module_is_the_real_extension():
    """Guards against a same-named file in the repo shadowing the wheel."""
    assert "site-packages" in str(knf.__file__), (
        f"kaldi_native_fbank resolved to {knf.__file__}; the native wheel should win"
    )


def test_frame_count_matches_kaldi_snip_edges():
    # Kaldi: 1 + (num_samples - window_size) // frame_shift; 400 / 160 @ 16 kHz
    for seconds, expected in ((1.0, 98), (0.5, 48), (0.025, 1), (0.01, 0)):
        feats = _features(knf, np.zeros(int(16000 * seconds)))
        assert feats.shape[0] == expected, seconds


def test_feature_shape_and_finiteness():
    feats = _features(knf, np.random.RandomState(0).randn(16000) * 1000)
    assert feats.shape == (98, 80)
    assert np.all(np.isfinite(feats))


def test_rejects_mismatched_sampling_frequency():
    """The reference implementation validates the rate (native does not)."""
    if not REFERENCE.exists():
        pytest.skip("numpy fbank reference not present")
    reference = _load_reference()
    fb = reference.OnlineFbank(_options(reference))
    with pytest.raises(Exception):
        fb.accept_waveform(8000, [0.0] * 16000)


def test_reference_matches_native_at_dither_zero():
    """The NumPy reference must be numerically equivalent to the native wheel."""
    if not REFERENCE.exists():
        pytest.skip("numpy fbank reference not present")
    reference = _load_reference()
    wave = np.random.RandomState(7).randn(16000) * 800
    native = _features(knf, wave, dither=0.0)
    shim = _features(reference, wave, dither=0.0)
    assert native.shape == shim.shape
    diff = np.abs(native - shim)
    # ~1e-2 max residual: the two build the mel matrix from slightly different
    # frequency grids. Measured on real speech: max 1.4e-2, corr 0.9999997.
    assert diff.max() < 5e-2, f"max abs diff {diff.max():.3e}"
    assert np.corrcoef(native.ravel(), shim.ravel())[0, 1] > 0.9999


def test_reference_matches_native_with_dither_enabled():
    """Dither uses a different noise sequence but stays numerically equivalent.

    Kaldi draws dither from its own RandGauss stream, which the reference does
    not reproduce bit-for-bit. Dither is tiny relative to the 1<<15-scaled
    waveform, so the log-mel features still agree closely (measured max ~5.8e-2
    against feature magnitudes around 10-21, i.e. well under 1%).
    """
    if not REFERENCE.exists():
        pytest.skip("numpy fbank reference not present")
    reference = _load_reference()
    wave = np.random.RandomState(11).randn(16000) * 800
    native = _features(knf, wave, dither=1.0)
    shim = _features(reference, wave, dither=1.0)
    diff = np.abs(native - shim)
    # Dither is ~1 LSB on a 1<<15-scaled waveform, so feature-level impact stays
    # far below 1% of the log-mel magnitude even though the noise sequences are
    # unrelated. Bounds are deliberately loose to remain deterministic across
    # waveforms; the point is "no order-of-magnitude divergence", not bit-equality.
    assert diff.max() < 2e-1, f"max abs diff {diff.max():.3e}"
    assert diff.max() / np.abs(native).mean() < 0.03, (
        f"relative divergence {diff.max() / np.abs(native).mean():.4f}"
    )


def test_native_accepts_any_sampling_frequency_label():
    """The native extension trusts the caller: it does not validate the rate.

    The reference implementation raises instead. This test pins the *native*
    behaviour so the difference is documented rather than surprising.
    """
    fb = knf.OnlineFbank(_options(knf))
    fb.accept_waveform(8000, [0.0] * 16000)
    assert fb.num_frames_ready == 98


# ------------------------------------------------------- funasr_onnx compat
class _FakeSession:
    """Single-output graph with the real sherpa-onnx input names."""

    def __init__(self, n_frames_out=None):
        self.calls = []
        self.n_frames_out = n_frames_out

    def get_inputs(self):
        return [type("I", (), {"name": n})() for n in
                ("x", "x_length", "language", "text_norm")]

    def get_outputs(self):
        return [type("O", (), {"name": "logits"})()]

    def run(self, output_names, payload, run_options=None):
        self.calls.append((output_names, payload))
        n, t = payload["x"].shape[0], payload["x"].shape[1]
        out_t = self.n_frames_out if self.n_frames_out is not None else t
        return [np.zeros((n, out_t, 25055), dtype=np.float32)]


class _TwoOutputSession(_FakeSession):
    def get_outputs(self):
        return [type("O", (), {"name": n})() for n in ("logits", "encoder_out_lens")]

    def run(self, output_names, payload, run_options=None):
        self.calls.append((output_names, payload))
        n, t = payload["x"].shape[0], payload["x"].shape[1]
        return [
            np.zeros((n, t, 25055), dtype=np.float32),
            np.full((n,), t, dtype=np.int32),
        ]


def _install():
    pytest.importorskip("funasr_onnx", reason="local-asr extra not installed")
    from ingest2md.transcription import funasr_onnx_compat
    funasr_onnx_compat.patch_funasr_onnx()
    from funasr_onnx.utils.utils import OrtInferSession
    return OrtInferSession


def test_patch_is_not_needed_for_two_output_graphs():
    session = _TwoOutputSession()
    status = compat.adapt_session(session)
    assert status.startswith("not needed")
    # Session must be left completely untouched.
    out = session.run(["logits", "encoder_out_lens"], {"x": np.zeros((1, 50, 560), np.float32)})
    assert len(out) == 2


def test_single_output_sensevoice_session_is_adapted():
    session = _FakeSession()
    status = compat.adapt_session(session)
    assert status.startswith("adapted")
    logits, lens = session.run(
        ["logits"],
        {
            "x": np.zeros((1, 200, 560), np.float32),
            "x_length": np.array([200], np.int32),
            "language": np.array([0], np.int32),
            "text_norm": np.array([15], np.int32),
        },
    )
    assert logits.shape == (1, 200, 25055)
    assert list(lens) == [200]


def test_adapt_is_idempotent():
    session = _FakeSession()
    first = compat.adapt_session(session)
    second = compat.adapt_session(session)
    assert first == second


def test_encoded_length_is_clamped_to_logits_extent():
    """A short logits tensor must never produce an out-of-range slice bound."""
    session = _FakeSession(n_frames_out=137)
    compat.adapt_session(session)
    logits, lens = session.run(
        ["logits"],
        {
            "x": np.zeros((1, 200, 560), np.float32),
            "x_length": np.array([200], np.int32),
            "language": np.array([0], np.int32),
            "text_norm": np.array([15], np.int32),
        },
    )
    assert logits.shape[1] == 137
    assert list(lens) == [137]


def test_missing_feats_length_is_tolerated():
    session = _FakeSession()
    compat.adapt_session(session)
    logits, lens = session.run(
        ["logits"],
        {
            "x": np.zeros((1, 40, 560), np.float32),
            "language": np.array([0], np.int32),
            "text_norm": np.array([15], np.int32),
        },
    )
    assert list(lens) == [40]


def test_non_sensevoice_single_output_graph_is_left_alone():
    """A 1-output graph with foreign input names must be skipped, not patched."""
    class Foreign(_FakeSession):
        def get_inputs(self):
            return [type("I", (), {"name": n})() for n in ("a", "b", "c", "d")]

    session = Foreign()
    status = compat.adapt_session(session)
    assert status.startswith("not applicable")
    # Original run() still returns a single-element list.
    out = session.run(["logits"], {"x": np.zeros((1, 10, 560), np.float32)})
    assert len(out) == 1


def test_unrelated_single_input_graph_is_left_alone():
    class Other(_FakeSession):
        def get_inputs(self):
            return [type("I", (), {"name": "waveform"})()]

    session = Other()
    status = compat.adapt_session(session)
    assert status.startswith("not applicable")


def test_real_sensevoice_model_adapter_end_to_end():
    """Runs the actual ONNX weights through funasr_onnx when they are present.

    Guarded on the whole ASR stack: ``funasr_onnx`` itself imports
    ``kaldi_native_fbank``, which is absent unless the ``local-asr`` extra is
    installed (CI installs only ``.[test]``).
    """
    pytest.importorskip("funasr_onnx", reason="local-asr extra not installed")
    pytest.importorskip("kaldi_native_fbank", reason="local-asr extra not installed")
    model_dir = ROOT / ".modelscope-cache" / "sherpa-sensevoice"
    audio = ROOT / ".modelscope-cache" / "example" / "zh.mp3"
    if not (model_dir / "model.onnx").exists() or not audio.exists():
        pytest.skip("SenseVoice ONNX weights / example audio not present")
    from funasr_onnx import SenseVoiceSmall

    model = SenseVoiceSmall(str(model_dir), batch_size=1, quantize=False)
    assert compat.adapt_session(model.ort_infer.session).startswith("adapted")
    text = model(str(audio), language="auto", textnorm="woitn")
    text = text[0] if isinstance(text, (list, tuple)) else text
    # Decoder reads Chinese numerals here, so assert the stable part of the
    # utterance rather than an ITN-dependent rendering.
    assert "开饭时间早上" in text, text
