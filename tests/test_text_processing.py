from __future__ import annotations

from app.services.text_processing import TextProcessor


def test_split_sentences_preserves_original_offsets() -> None:
    processor = TextProcessor()
    content = "第一句保证收益。 第二句评论区领取资料！\n第三句正常说明。"

    cleaned = processor.clean_text(content)
    segments = processor.split_sentences(content)

    assert cleaned == "第一句保证收益。 第二句评论区领取资料！\n第三句正常说明。"
    assert len(segments) == 3
    assert segments[0].text == "第一句保证收益。"
    assert content[segments[0].start : segments[0].end] == "第一句保证收益。"
    assert segments[1].text == "第二句评论区领取资料！"
    assert content[segments[1].start : segments[1].end] == "第二句评论区领取资料！"


def test_split_sentences_breaks_on_newlines_without_terminal_punctuation() -> None:
    processor = TextProcessor()
    content = "第一行提到辍学风险\n第二行是正常描述\n第三行继续说明"

    segments = processor.split_sentences(content)

    assert [item.text for item in segments] == [
        "第一行提到辍学风险",
        "第二行是正常描述",
        "第三行继续说明",
    ]
