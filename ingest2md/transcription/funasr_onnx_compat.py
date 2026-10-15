"""Adapt a *single* SenseVoice ONNX runtime session when its graph has one output.

funasr_onnx 0.4.3 expects (logits, encoder_out_lens), while certain
four-input SenseVoice exports expose only logits. This adapter does not
modify funasr_onnx itself or patch ONNX Runtime globally.
"""
from __future__ import annotations

import numpy as np

_INPUT_ALIASES = {
    "feats": ("x", "speech", "feats", "input"),
    "feats_len": ("x_length", "speech_lengths", "feats_len"),
    "language": ("language", "language_id"),
    "textnorm": ("text_norm", "textnorm"),
}
_MARKER = "_ingest2md_compat_status"


def _names(session, method: str) -> list[str]:
    return [str(item.name) for item in getattr(session, method)()]


def adapt_session(session) -> str:
    """Adapt only recognized single-output, four-input SenseVoice sessions.

    The missing valid-frame lengths include control tokens added by the
    particular graph. The offset is inferred from output vs padded input
    time extent rather than hardcoded. All lengths are clamped to logits.
    """
    previous = getattr(session, _MARKER, None)
    if previous is not None:
        return previous

    inputs = _names(session, "get_inputs")
    outputs = _names(session, "get_outputs")
    if len(outputs) >= 2:
        status = f"not needed ({len(outputs)} outputs)"
        setattr(session, _MARKER, status)
        return status

    if len(outputs) != 1 or len(inputs) != 4:
        status = f"not applicable ({len(inputs)} inputs, {len(outputs)} outputs)"
        setattr(session, _MARKER, status)
        return status

    by_lower = {value.lower(): value for value in inputs}
    mapped = {}
    for field, aliases in _INPUT_ALIASES.items():
        name = next((by_lower[alias] for alias in aliases if alias in by_lower), None)
        if name is None:
            status = f"not applicable (missing {field}, inputs={inputs!r})"
            setattr(session, _MARKER, status)
            return status
        mapped[field] = name

    original_run = session.run

    def run_with_lengths(requested_outputs, payload, run_options=None):
        results = original_run(requested_outputs, payload, run_options)
        if not isinstance(results, (list, tuple)) or len(results) != 1:
            raise RuntimeError("Single-output SenseVoice session returned unexpected result count")
        logits = np.asarray(results[0])
        feats = np.asarray(payload[mapped["feats"]])
        if logits.ndim != 3 or feats.ndim != 3 or logits.shape[0] != feats.shape[0]:
            raise RuntimeError(
                f"SenseVoice shapes incompatible: input={feats.shape}, logits={logits.shape}"
            )

        batch, padded_input_time = feats.shape[:2]
        output_time = logits.shape[1]
        extra_control_frames = max(0, output_time - padded_input_time)
        raw_lengths = payload.get(mapped["feats_len"])
        if raw_lengths is None:
            lengths = np.full((batch,), output_time, dtype=np.int64)
        else:
            lengths = np.asarray(raw_lengths, dtype=np.int64).reshape(-1)
            if len(lengths) != batch or np.any(lengths < 0) or np.any(lengths > padded_input_time):
                raise RuntimeError(f"Invalid input feature lengths for batch size {batch}")
            lengths = np.clip(lengths + extra_control_frames, 0, output_time)
        return [logits, lengths.astype(np.int64)]

    session.run = run_with_lengths
    status = f"adapted (one-output SenseVoice; inputs={list(mapped.values())})"
    setattr(session, _MARKER, status)
    return status
