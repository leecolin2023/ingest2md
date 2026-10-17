from __future__ import annotations

import json

import pytest

from ingest2md.config import Settings
from ingest2md.transcription.model import Segment
from ingest2md.transcription.normalization import NormalizationHints
from ingest2md.transcription import normalization_llm


def test_applies_exact_local_patch_and_preserves_untouched_text():
    source = [
        "我们讨论的是 deep seek 的 API，以及其他事情。",
        "第二段保持原样。",
    ]

    output, warnings = normalization_llm._validate_and_apply_edits(
        {
            "edits": [
                {"id": 0, "old": "deep seek", "new": "DeepSeek"},
            ]
        },
        [0, 1],
        source,
    )

    assert output == [
        "我们讨论的是 DeepSeek 的 API，以及其他事情。",
        source[1],
    ]
    assert warnings == []


def test_empty_edit_list_returns_original_text_unchanged():
    source = ["没有需要修改的内容。", "保留原始空格  "]

    output, warnings = normalization_llm._validate_and_apply_edits(
        {"edits": []}, [0, 1], source
    )

    assert output == source
    assert warnings == []


def test_rejects_full_segment_rewrite():
    source = ["这是一整段原文，不能被整体替换。"]

    output, warnings = normalization_llm._validate_and_apply_edits(
        {"edits": [{"id": 0, "old": source[0], "new": "模型改写后的整段内容。"}]},
        [0],
        source,
    )

    assert output == source
    assert any("整段文本" in warning for warning in warnings)


def test_rejects_ambiguous_old_substring_without_changing_text():
    source = ["这里提到了 AI，也再次提到了 AI。"]

    output, warnings = normalization_llm._validate_and_apply_edits(
        {"edits": [{"id": 0, "old": "AI", "new": "Artificial Intelligence"}]},
        [0],
        source,
    )

    assert output == source
    assert any("无法唯一定位" in warning for warning in warnings)


def test_rejects_context_or_out_of_window_segment_id_but_applies_valid_edit():
    ids = [5, 6]
    source = ["deep seek 是模型。", "这段不需要改。"]

    output, warnings = normalization_llm._validate_and_apply_edits(
        {
            "edits": [
                {"id": 4, "old": "deep seek", "new": "DeepSeek"},
                {"id": 5, "old": "deep seek", "new": "DeepSeek"},
            ]
        },
        ids,
        source,
    )

    assert output == ["DeepSeek 是模型。", source[1]]
    assert len(warnings) == 1
    assert "不属于本次 target_segments" in warnings[0]


def test_rejects_both_overlapping_patches_instead_of_order_dependent_apply():
    source = ["ABCDE 的后续文本。"]

    output, warnings = normalization_llm._validate_and_apply_edits(
        {
            "edits": [
                {"id": 0, "old": "BCD", "new": "X"},
                {"id": 0, "old": "CD", "new": "Y"},
            ]
        },
        [0],
        source,
    )

    assert output == source
    assert len(warnings) == 2
    assert all("重叠" in warning for warning in warnings)


def test_local_patch_leaves_numbers_and_negation_untouched():
    source = ["不是 100 个 work body，后续再讨论。"]

    output, warnings = normalization_llm._validate_and_apply_edits(
        {"edits": [{"id": 0, "old": "work body", "new": "WorkBuddy"}]},
        [0],
        source,
    )

    assert output == ["不是 100 个 WorkBuddy，后续再讨论。"]
    assert warnings == []


def test_normalize_window_requests_and_applies_patch_edits(monkeypatch):
    source = "我们讨论的是 deep seek 的 API。"
    segments = [Segment(0, 30, source)]

    def fake_post(settings, path, payload, session_id):
        assert path == "/chat/completions"
        request = json.loads(payload["messages"][1]["content"])
        assert request["target_segments"] == [{"id": 0, "text": source}]
        assert request["required_output"]["edits"][0]["id"] == 0
        return {
            "choices": [{
                "message": {
                    "content": json.dumps(
                        {"edits": [{"id": 0, "old": "deep seek", "new": "DeepSeek"}]},
                        ensure_ascii=False,
                    )
                }
            }]
        }

    monkeypatch.setattr(normalization_llm, "_post", fake_post)
    output, warnings = normalization_llm._normalize_window(
        segments,
        0,
        1,
        NormalizationHints(),
        Settings(llm_api_key="test"),
        "mock-model",
        "session",
    )

    assert output == ["我们讨论的是 DeepSeek 的 API。"]
    assert warnings == []


def test_malformed_model_json_falls_back_to_original_window(monkeypatch):
    source = [Segment(0, 30, "这里是原始 basic 文本。")]

    monkeypatch.setattr(
        normalization_llm,
        "_post",
        lambda *args, **kwargs: {
            "choices": [{"message": {"content": "not JSON"}}]
        },
    )
    output, model, warnings = normalization_llm.normalize_segments_with_llm(
        source,
        NormalizationHints(),
        Settings(llm_api_key="test", normalization_model="mock-model"),
    )

    assert output == [source[0].text]
    assert model == "mock-model"
    assert len(warnings) == 1
    assert "保留 basic 结果" in warnings[0]


def test_rejects_legacy_full_segment_response_schema():
    with pytest.raises(RuntimeError, match="edits"):
        normalization_llm._validate_and_apply_edits(
            {"segments": [{"id": 0, "text": "改写后的整段文本"}]},
            [0],
            ["原始整段文本"],
        )
