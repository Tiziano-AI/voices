"""Transient create-flow contracts used by voice creation workflows."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from voices.domain.contracts import (
    _validate_non_empty,
    _validate_supported_language,
    _validate_voice_id,
)

GUIDED_RECORDING_SCRIPTS = {
    "Chinese": (
        "夜里安静下来时，我能听见走廊里最轻的回响，也能听见水壶在鸣叫前那一瞬的犹豫。接着语气一转，我会站定、做出决定，让整间屋子的空气都跟着收紧。可下一秒我又会笑出来，因为再大的把握，有时也会穿着拖鞋慢慢走来。等我把话再说一遍，语速放缓，尾音却更坚定，像是在把一件重要的事轻轻放到你手里。你有没有发现，声音可以从耳语走到承诺，却一直保留温度？"
    ),
    "English": (
        "When the house falls quiet, I can hear the smallest hinge in the hallway "
        "and the kettle thinking before it sings. "
        "Then the mood shifts: I step forward, I make the decision, and the room follows. "
        "A moment later I laugh at myself, because some days even certainty arrives in socks. "
        "I say the next line more slowly, with a little more weight, "
        "as if a private thought has decided it can stand in the light. "
        "Did you notice how a voice can move from a whisper to a promise without losing its warmth?"
    ),
    "French": (
        "Quand la maison se tait, j'entends la moindre charnière du couloir "
        "et la bouilloire qui hésite juste avant de chanter. "
        "Puis le ton change: j'avance, je tranche, et toute la pièce se met à me suivre. "
        "Une seconde plus tard, j'en ris moi-même, parce qu'il arrive même à la certitude d'entrer en pantoufles. "
        "Je reprends alors plus lentement, avec une gravité douce, "
        "comme si une confidence choisissait enfin de tenir debout. "
        "Tu l'as remarqué, toi aussi, comme une voix peut passer du murmure à la promesse sans perdre sa chaleur?"
    ),
    "German": (
        "Wenn das Haus still wird, höre ich sogar das kleinste Scharnier im Flur "
        "und den Wasserkocher, kurz bevor er zu singen beginnt. "
        "Dann kippt die Stimmung: Ich trete nach vorn, treffe die Entscheidung, und der ganze Raum zieht mit. "
        "Einen Augenblick später muss ich darüber lächeln, "
        "denn manchmal kommt selbst Gewissheit in Hausschuhen herein. "
        "Dann nehme ich Tempo heraus und gebe dem nächsten Satz mehr Gewicht, "
        "als würde ein stiller Gedanke plötzlich Haltung annehmen. "
        "Merkst du, wie eine Stimme vom Flüstern in ein Versprechen wechseln kann, ohne ihre Wärme zu verlieren?"
    ),
    "Italian": (
        "Quando la casa tace, sento perfino la cerniera della porta in fondo al corridoio "
        "e il bollitore che trattiene il fiato prima di cantare. "
        "Poi il tono cambia: faccio un passo avanti, prendo la decisione, e la stanza mi segue. "
        "Un attimo dopo mi viene da sorridere, perché a volte perfino la certezza arriva in pantofole. "
        "Alla frase successiva rallento appena e do più peso alle parole, "
        "come se una confidenza privata decidesse finalmente di restare in piedi. "
        "Hai notato come una voce possa passare da un sussurro a una promessa senza perdere calore?"
    ),
    "Japanese": (
        "家の中が静かになると、廊下のいちばん小さなきしみや、やかんが鳴く直前のためらいまで聞こえてくる。"
        "そこから空気が変わる。私は一歩前に出て、決めるべきことを決め、部屋の気配までこちらに向き直らせる。"
        "でも次の瞬間には、そんな自分に少し笑ってしまう。確信だって、ときには部屋着のままゆっくり現れるからだ。"
        "そして次の一文では、少しだけ速度を落とし、内緒話がそのまま意志になるように言葉へ重みをのせる。"
        "声はささやきから約束へ変わっても、温度を失わずにいられると思わない？"
    ),
    "Korean": (
        "집 안이 조용해지면 복도 끝 문짝의 작은 떨림도 들리고, 주전자가 울기 직전 숨을 고르는 소리도 들린다. "
        "그러다 분위기가 바뀐다. 나는 한 걸음 앞으로 나서고, 결정을 내리고, 방 안의 공기까지 따라오게 만든다. "
        "그런데 바로 다음 순간에는 스스로 웃게 된다. 때로는 확신조차 슬리퍼를 끌며 천천히 들어오기 때문이다. "
        "그리고 다음 문장에서는 속도를 조금 늦추고 무게를 더한다. 마치 혼잣말이 갑자기 의지가 되는 순간처럼. "
        "목소리가 속삭임에서 약속으로 넘어가면서도 온기를 잃지 않을 수 있다는 걸, 너도 느끼니?"
    ),
    "Portuguese": (
        "Quando a casa fica em silêncio, eu escuto até a dobradiça mais discreta do corredor "
        "e a chaleira pensando antes de cantar. "
        "Depois o clima muda: eu dou um passo à frente, tomo a decisão, e o quarto inteiro vem comigo. "
        "Um instante depois eu sorrio de mim mesmo, porque às vezes até a certeza entra de pantufas. "
        "Na frase seguinte eu diminuo o ritmo e deixo a voz ganhar peso, "
        "como se uma ideia íntima resolvesse finalmente ocupar o centro da sala. "
        "Você já percebeu como uma voz pode sair de um sussurro e virar promessa sem perder o calor?"
    ),
    "Russian": (
        "Когда в доме становится тихо, я слышу даже самую лёгкую петлю в коридоре "
        "и чайник, который медлит перед тем, как запеть. "
        "Потом всё меняется: я делаю шаг вперёд, принимаю решение, "
        "и вся комната словно собирается вокруг этого движения. "
        "А через секунду я уже усмехаюсь себе, потому что иногда даже уверенность "
        "входит в комнату в домашних тапочках. "
        "Следующую фразу я произношу медленнее и плотнее, словно тихая мысль вдруг решает стать поступком. "
        "Ты замечал, как голос может перейти от шёпота к обещанию и при этом не потерять тепло?"
    ),
    "Spanish": (
        "Cuando la casa se queda en silencio, alcanzo a oír hasta la bisagra más pequeña del pasillo "
        "y la tetera pensando antes de cantar. "
        "Luego el aire cambia: doy un paso al frente, tomo la decisión, y toda la habitación se ordena conmigo. "
        "Un segundo después me sale una sonrisa, porque a veces hasta la certeza entra en pantuflas. "
        "En la frase siguiente bajo un poco el ritmo y dejo más peso en la voz, "
        "como si una confidencia eligiera convertirse en decisión. "
        "¿Te has fijado en que una voz puede ir del susurro a la promesa sin perder calidez?"
    ),
}


def get_guided_recording_script(language: str) -> str:
    """Return the curated guided recording script for one supported language."""
    resolved_language = _validate_supported_language(language)
    return GUIDED_RECORDING_SCRIPTS[resolved_language]


class CloneReviewRequest(BaseModel):
    """Canonical post-capture review request shared by clone and record ingresses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: str
    review_policy: Literal["import", "record_guided", "record_free"] = "import"
    transcript: str | None = None
    requested_name: str | None = None
    requested_voice_id: str | None = None
    fallback_name: str

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize review-request language labels."""
        return _validate_supported_language(value)

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str | None) -> str | None:
        """Normalize optional approved transcripts."""
        if value is None:
            return None
        return _validate_non_empty("transcript", value)

    @field_validator("requested_name", "fallback_name")
    @classmethod
    def validate_name(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Reject blank names when a review request provides them."""
        if value is None:
            return None
        field_name = info.field_name or "value"
        return _validate_non_empty(field_name.replace("_", " "), value)

    @field_validator("requested_voice_id")
    @classmethod
    def validate_voice_id(cls, value: str | None) -> str | None:
        """Reject invalid optional requested voice identifiers."""
        if value is None:
            return None
        return _validate_voice_id(value)


class TranscriptionSegment(BaseModel):
    """One transcription segment projected into the product surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    language: str
    start: float
    end: float

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject blank segment text."""
        return _validate_non_empty("segment text", value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize segment language labels."""
        return _validate_supported_language(value)

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: float) -> float:
        """Require non-negative segment times."""
        if value < 0:
            raise ValueError("segment time must be non-negative")
        return value


class TranscriptionDraft(BaseModel):
    """Canonical transcript draft returned before clone save."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transcript: str
    language: str
    duration_seconds: float
    segments: list[TranscriptionSegment]

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str) -> str:
        """Reject blank transcript drafts."""
        return _validate_non_empty("transcript", value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize draft language labels."""
        return _validate_supported_language(value)

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require positive durations."""
        if value <= 0:
            raise ValueError("duration_seconds must be positive")
        return value
