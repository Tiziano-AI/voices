import pytest

from voices.domain.errors import InvalidPromptFileError
from voices.util.prompt_loader import load_prompts


def test_jsonl_valid(tmp_path):
    prompt_file = tmp_path / "prompts.jsonl"
    prompt_file.write_text(
        '{"id":"v1","instruct":"Low narrator"}\n{"id":"v2","instruct":"Bright host","name":"Bright Host"}\n',
        encoding="utf-8",
    )
    prompts = load_prompts(prompt_file, default_text="Hello.", default_language="English")
    assert len(prompts) == 2
    assert prompts[0].id == "v1"
    assert prompts[0].name == "V1"
    assert prompts[0].text == "Hello."
    assert prompts[1].name == "Bright Host"


def test_jsonl_per_line_overrides(tmp_path):
    prompt_file = tmp_path / "prompts.jsonl"
    prompt_file.write_text(
        '{"id":"v1","instruct":"x","text":"Custom text","language":"Chinese"}\n',
        encoding="utf-8",
    )
    prompts = load_prompts(prompt_file, default_text="Default.", default_language="English")
    assert prompts[0].text == "Custom text"
    assert prompts[0].language == "Chinese"


def test_jsonl_missing_instruct(tmp_path):
    prompt_file = tmp_path / "prompts.jsonl"
    prompt_file.write_text('{"id":"v1"}\n', encoding="utf-8")
    with pytest.raises(InvalidPromptFileError, match="invalid prompt entry"):
        load_prompts(prompt_file, default_text="Hello.", default_language="English")


def test_jsonl_missing_id(tmp_path):
    prompt_file = tmp_path / "prompts.jsonl"
    prompt_file.write_text('{"instruct":"Low narrator"}\n', encoding="utf-8")
    with pytest.raises(InvalidPromptFileError, match="invalid prompt entry"):
        load_prompts(prompt_file, default_text="Hello.", default_language="English")


def test_jsonl_malformed_json(tmp_path):
    prompt_file = tmp_path / "prompts.jsonl"
    prompt_file.write_text("not json\n", encoding="utf-8")
    with pytest.raises(InvalidPromptFileError, match="Malformed JSON"):
        load_prompts(prompt_file, default_text="Hello.", default_language="English")


def test_txt_valid(tmp_path):
    prompt_file = tmp_path / "prompts.txt"
    prompt_file.write_text("Low smoky narrator\n# comment\n\nBright radio host\n", encoding="utf-8")
    prompts = load_prompts(prompt_file, default_text="Hello.", default_language="English")
    assert len(prompts) == 2
    assert prompts[0].text == "Hello."
    assert prompts[0].instruct == "Low smoky narrator"


def test_txt_requires_default_text(tmp_path):
    prompt_file = tmp_path / "prompts.txt"
    prompt_file.write_text("Some prompt\n", encoding="utf-8")
    with pytest.raises(InvalidPromptFileError, match="--text"):
        load_prompts(prompt_file, default_text=None, default_language="English")


def test_unsupported_extension(tmp_path):
    prompt_file = tmp_path / "prompts.csv"
    prompt_file.write_text("a,b,c\n", encoding="utf-8")
    with pytest.raises(InvalidPromptFileError, match="Unsupported"):
        load_prompts(prompt_file, default_text="Hello.", default_language="English")


def test_jsonl_blank_lines_skipped(tmp_path):
    prompt_file = tmp_path / "prompts.jsonl"
    prompt_file.write_text('\n{"id":"v1","instruct":"x"}\n\n', encoding="utf-8")
    prompts = load_prompts(prompt_file, default_text="Hello.", default_language="English")
    assert len(prompts) == 1
