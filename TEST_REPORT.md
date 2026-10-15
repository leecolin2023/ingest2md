# ingest2md v0.10.2 Test Report

## CI verification

Feature branch: `fix/sensevoice-runtime-compatibility`
GitHub Actions run: `38711627556`
Result: **success** — all four jobs passed.

| Job | Result | Coverage |
|---|---|---|
| test (3.10) | PASS | Base install; compileall; full pytest; CLI |
| test (3.12) | PASS | Base install; compileall; full pytest; CLI |
| local-asr-install (3.10) | PASS | Clean `.[local-asr,test]`, `pip check`, native imports, adapter tests |
| local-asr-install (3.12) | PASS | Clean `.[local-asr,test]`, `pip check`, native imports, adapter tests |

## v0.10.2 regression coverage

- Inference-only `local-asr`: `funasr-onnx==0.4.3` plus `modelscope`; no model export stack.
- Default pre-exported ONNX resolution and narrow tokenizer download.
- Missing required model files fail explicitly rather than trigger implicit export.
- Single-output four-input SenseVoice session adaptation is instance-local.
- Existing two-output graphs and unrelated input signatures are untouched.
- Batched valid lengths include inferred extra control frames and are clamped to logits.
- ITN passes `textnorm=withitn/woitn`.
- Compatibility tests run under normal `.[test]` and with optional local-ASR installed.
- Existing router, source adapters, runtime and batch regression tests remain in the suite.

## Limitations

CI validates dependency installation, imports, interface contracts and regressions. It does not download large SenseVoice weights or run real speech end-to-end. Validate real model/audio quality and performance on a target machine before production claims.
