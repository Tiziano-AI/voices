from voices.util.slug import display_name_from_voice_id, slugify, voice_id_from_name, voice_id_from_prompt


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"


def test_slugify_punctuation():
    assert slugify("Low, smoky, restrained!") == "low-smoky-restrained"


def test_slugify_max_length():
    result = slugify("a" * 100, max_length=10)
    assert len(result) <= 10


def test_slugify_strips_trailing_hyphens():
    result = slugify("hello---", max_length=40)
    assert not result.endswith("-")


def test_slugify_empty():
    assert slugify("") == ""


def test_slugify_all_punctuation():
    assert slugify("!!!???") == ""


def test_voice_id_from_prompt_deterministic():
    a = voice_id_from_prompt("Low, smoky narrator")
    b = voice_id_from_prompt("Low, smoky narrator")
    assert a == b


def test_voice_id_from_prompt_has_hash_suffix():
    result = voice_id_from_prompt("Fast, bright radio host")
    parts = result.rsplit("-", 1)
    assert len(parts) == 2
    assert len(parts[1]) == 6


def test_voice_id_from_prompt_different_inputs_differ():
    a = voice_id_from_prompt("Calm narrator")
    b = voice_id_from_prompt("Excited narrator")
    assert a != b


def test_voice_id_from_name_falls_back_to_voice():
    assert voice_id_from_name("!!!") == "voice"


def test_display_name_from_voice_id_titles_words():
    assert display_name_from_voice_id("my_voice-id") == "My Voice Id"
