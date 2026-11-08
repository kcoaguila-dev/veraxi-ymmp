from veraxi_ymmp.editorial.script_ingest import (
    parse_markdown_dialogue,
    split_text_to_char_limit,
    normalize_speaker,
)


def test_normalize_speaker() -> None:
    assert normalize_speaker("Zundamon") == "ずんだもん"
    assert normalize_speaker("[ずんだもん]") == "ずんだもん"
    assert normalize_speaker("**Metan**") == "四国めたん"
    assert normalize_speaker("tsumugi") == "春日部つむぎ"
    assert normalize_speaker("Unknown") is None


def test_split_text_to_char_limit_under_ceiling() -> None:
    short_text = "こんにちはなのだ！"
    chunks = split_text_to_char_limit(short_text, max_chars=38)
    assert chunks == [short_text]


def test_split_text_to_char_limit_exceeding_ceiling() -> None:
    long_text = "ボクの持っている株が明日大暴落するなんて信じられないのだ！今すぐ全部売って現金に換えてくるのだー！"
    chunks = split_text_to_char_limit(long_text, max_chars=38)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 38


def test_parse_markdown_dialogue_valid_script() -> None:
    md_content = """
# NotebookLM Response

[Zundamon]: ボクの株、明日売っ払ってくるのだー！
**Metan**: 底値で狼狽売りする養分の鑑ですわね。
3. [Tsumugi]: でもサーバ室のログ見たら、先週からエラー出てたっすよ。
"""
    entries = parse_markdown_dialogue(md_content)
    assert len(entries) == 3

    assert entries[0]["character"] == "ずんだもん"
    assert entries[0]["character_position"] == "right"
    assert entries[0]["emotion"] == "excited"

    assert entries[1]["character"] == "四国めたん"
    assert entries[1]["character_position"] == "left"

    assert entries[2]["character"] == "春日部つむぎ"
    assert entries[2]["character_position"] == "right"

    # Invariants for cuts 0-2 (Cold Open)
    for i in range(3):
        assert entries[i]["image"] is None
