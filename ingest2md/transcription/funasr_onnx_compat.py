"""Compatibility shim for running single-output SenseVoice ONNX exports.

The vendored ``funasr_onnx`` package and the ONNX weights are left untouched;
this module adapts the two at the point where they meet -- the inference
session.

Why it is needed
----------------
``funasr_onnx.sensevoice_bin.SenseVoiceSmall.infer`` does::

    ctc_logits, encoder_out_lens = self.ort_infer([feats, feats_len, lang, tnorm])

which assumes the ONNX graph exposes **two** outputs. The sherpa-onnx SenseVoice
export declares one (``export-onnx.py``: ``output_names=["logits"]``), so the
unpack raises ``ValueError: not enough values to unpack (expected 2, got 1)``.

How the missing value is derived
--------------------------------
That same export prepends three control embeddings and adjusts the length::

    x = torch.cat((language_query, event_emo_query, text_norm_query, x), dim=1)
    x_length += 4
    encoder_out, encoder_out_lens = self.encoder(x, x_length)

so the encoder emits ``T + 4`` frames for ``T`` input frames (measured 204 for
200). The only downstream use is the slice ``ctc_logits[b, :lens[b], :]``, i.e.
a slice bound. We return the input feature lengths **clamped to the actual
logits extent**: it can never index past the tensor, and it avoids baking a
``+4`` constant into the project, since that constant describes one particular
export rather than SenseVoice in general.

Design: inspect, then adapt one session
---------------------------------------
Earlier this module monkey-patched ``OrtInferSession.__call__`` process-wide at
import time. That was too broad and could not tell "not needed" from "not
possible". Now the caller hands us the concrete session after it is built:

* the session's own input/output *names* decide whether anything happens at all;
* a graph that already exposes two outputs, or whose inputs are not the
  SenseVoice signature, is reported as ``skipped`` and left completely alone;
* the fix is applied to that one instance, not to the class.
"""
from __future__ import annotations

import numpy as np

_INPUT_ALIASES = {
    "feats": ("x", "speech", "feats", "input"),
    "feats_len": ("x_length", "speech_lengths", "feats_len"),
    "language": ("language", "language_id"),
    "textnorm": ("text_norm", "textnorm"),
}

# Sentinel so a skipped session is never re-inspected on every chunk.
_MARKER = "_ingest2md_compat"


def _session_input_names(session) -> list[str]:
    return [str(v.name) for v in session.get_inputs()]


def _session_output_names(session) -> list[str]:
    return [str(v.name) for v in session.get_outputs()]


def _resolve(names: dict[str, str], key: str) -> str:
    for alias in _INPUT_ALIASES[key]:
        if alias.lower() in names:
            return names[alias.lower()]
    raise KeyError(
        f"single-output session is not SenseVoice-shaped: cannot map '{key}' "
        f"to any of {_INPUT_ALIASES[key]} (graph inputs: {sorted(names.values())})"
    )


def adapt_session(session) -> str:
    """Make ``session`` usable by ``funasr_onnx``'s SenseVoice decoder.

    Returns a human-readable status. Safe to call repeatedly: the session is
    tagged once and returns immediately afterwards.
    """
    status = getattr(session, _MARKER, None)
    if status is not None:
        return status

    output_names = _session_output_names(session)
    input_names = _session_input_names(session)

    # Native FunASR exports already expose encoder_out_lens.
    if len(output_names) >= 2:
        status = f"not needed ({len(output_names)} outputs)"
        setattr(session, _MARKER, status)
        return status

    # Anything that is not the 4-input SenseVoice single-output shape is none of
    # our business; leave it exactly as it was.
    if len(output_names) != 1 or len(input_names) != 4:
        status = (
            f"not applicable (single output '{output_names[0] if output_names else '?'}' "
            f"but {len(input_names)} inputs)"
        )
        setattr(session, _MARKER, status)
        return status

    names = {name.lower(): name for name in input_names}
    try:
        mapped = {key: _resolve(names, key) for key in _INPUT_ALIASES}
    except KeyError as exc:
        status = f"not applicable ({exc})"
        setattr(session, _MARKER, status)
        return status

    original_run = session.run

    def run_with_lengths(requested_outputs, payload, run_options=None):
        results = original_run(requested_outputs, payload, run_options)
        logits = results[0]
        feats_len = payload.get(mapped["feats_len"])
        if feats_len is None:
            lengths = np.full((logits.shape[0],), logits.shape[1], dtype=np.int64)
        else:
            # Slice bound only; clamped so it can never exceed the real tensor.
            lengths = np.minimum(
                np.asarray(feats_len, dtype=np.int64).reshape(-1),
                int(logits.shape[1]),
            )
        return logits, lengths

    session.run = run_with_lengths
    status = (
        "adapted (single-output SenseVoice export; "
        f"inputs {list(mapped.values())})"
    )
    setattr(session, _MARKER, status)
    return status
