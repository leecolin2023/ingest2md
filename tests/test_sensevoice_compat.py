"""Pure unit tests for SenseVoice ONNX session contracts and model resolution.

These deliberately run under .[test] WITHOUT the local-asr extra.
An additional CI job installs .[local-asr,test] to check the real imports.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ingest2md.config import Settings
from ingest2md.transcription.funasr_onnx_compat import adapt_session
from ingest2md.transcription.sensevoice import (
    SenseVoiceBackend,
    _resolve_model_dir,
    _validate_onnx_model,
)


class FakeSession:
    def __init__(self, inputs=("x", "x_length", "language", "text_norm"),
                 outputs=("logits",), extra=4):
        self.inputs = inputs
        self.outputs = outputs
        self.extra = extra
        self.calls = 0

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in self.inputs]

    def get_outputs(self):
        return [SimpleNamespace(name=name) for name in self.outputs]

    def run(self, output_names, payload, run_options=None):
        self.calls += 1
        batch, time, _ = payload["x"].shape
        logits = np.zeros((batch, time + self.extra, 2), dtype=np.float32)
        if len(self.outputs) == 2:
            return [logits, np.array([time + self.extra] * batch, dtype=np.int64)]
        return [logits]


def _payload(batch=1, padded_time=200, lengths=(200,)):
    return {
        "x": np.zeros((batch, padded_time, 560), dtype=np.float32),
        "x_length": np.array(lengths, dtype=np.int32),
        "language": np.zeros((batch,), dtype=np.int32),
        "text_norm": np.full((batch,), 14, dtype=np.int32),
    }


def test_single_output_derives_control_frame_offset_without_hardcoding():
    session = FakeSession(extra=4)
    assert adapt_session(session).startswith("adapted")
    logits, lengths = session.run(["logits"], _payload())
    assert logits.shape == (1, 204, 2)
    assert lengths.tolist() == [204]


def test_padded_batch_lengths_preserve_control_frame_offset():
    session = FakeSession(extra=4)
    adapt_session(session)
    logits, lengths = session.run(
        ["logits"], _payload(batch=2, padded_time=200, lengths=(160, 200))
    )
    assert logits.shape[:2] == (2, 204)
    assert lengths.tolist() == [164, 204]


def test_output_shorter_than_input_clamps_valid_length():
    session = FakeSession(extra=-63)
    adapt_session(session)
    _, lengths = session.run(["logits"], _payload(padded_time=200))
    assert lengths.tolist() == [137]


def test_missing_input_lengths_uses_output_extent():
    session = FakeSession(extra=4)
    adapt_session(session)
    payload = _payload()
    del payload["x_length"]
    _, lengths = session.run(["logits"], payload)
    assert lengths.tolist() == [204]


def test_invalid_feature_length_fails_instead_of_guessing():
    session = FakeSession()
    adapt_session(session)
    with pytest.raises(RuntimeError, match="Invalid input feature lengths"):
        session.run(["logits"], _payload(lengths=(300,)))


def test_multi_output_graph_not_patched():
    session = FakeSession(outputs=("logits", "encoder_out_lens"))
    original_run = session.run
    assert adapt_session(session).startswith("not needed")
    assert session.run == original_run
    assert len(session.run(None, _payload())) == 2


def test_foreign_graph_unmodified():
    session = FakeSession(inputs=("a", "b", "c", "d"))
    original_run = session.run
    assert adapt_session(session).startswith("not applicable")
    assert session.run == original_run


def test_adapter_is_idempotent():
    session = FakeSession()
    first = adapt_session(session)
    method = session.run
    assert adapt_session(session) == first
    assert session.run is method


def test_sensevoice_uses_actual_textnorm_keyword():
    seen = []

    class Model:
        def __call__(self, paths, **kwargs):
            seen.append(kwargs)
            return ["hello"]

    assert SenseVoiceBackend._run_model(Model(), ["chunk.wav"], "auto", True) == ["hello"]
    assert seen == [{"language": "auto", "textnorm": "withitn"}]
    seen.clear()
    SenseVoiceBackend._run_model(Model(), ["chunk.wav"], "zh", False)
    assert seen == [{"language": "zh", "textnorm": "woitn"}]


def test_preexported_model_is_required(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="ONNX"):
        _validate_onnx_model(tmp_path, quantize=True)
    for name in ("model_quant.onnx", "config.yaml", "am.mvn",
                 "chn_jpn_yue_eng_ko_spectok.bpe.model"):
        (tmp_path / name).write_bytes(b"fixture")
    _validate_onnx_model(tmp_path, quantize=True)


def test_default_model_resolves_preexported_onnx_and_small_tokenizer(tmp_path: Path, monkeypatch):
    onnx = tmp_path / "onnx"
    base = tmp_path / "base"
    onnx.mkdir()
    base.mkdir()
    (base / "chn_jpn_yue_eng_ko_spectok.bpe.model").write_bytes(b"tokenizer")
    calls = []

    def snapshot_download(model, **kwargs):
        calls.append((model, kwargs))
        return str(onnx if model.endswith("-onnx") else base)

    monkeypatch.setitem(
        sys.modules, "modelscope",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    resolved = _resolve_model_dir(Settings())
    assert resolved == onnx
    assert (onnx / "chn_jpn_yue_eng_ko_spectok.bpe.model").read_bytes() == b"tokenizer"
    assert calls[0][0] == "iic/SenseVoiceSmall-onnx"
    assert calls[1] == (
        "iic/SenseVoiceSmall",
        {"allow_file_pattern": ["chn_jpn_yue_eng_ko_spectok.bpe.model"]},
    )


def test_explicit_model_directory_remains_unchanged(tmp_path: Path):
    assert _resolve_model_dir(Settings(sensevoice_model_dir=str(tmp_path))) == tmp_path
