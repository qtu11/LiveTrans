"""Dịch sang tiếng Việt bằng NLLB-200 (CTranslate2 int8) + sentencepiece."""

from __future__ import annotations

import re
from pathlib import Path

WHISPER_TO_NLLB: dict[str, str] = {
    "en": "eng_Latn", "zh": "zho_Hans", "yue": "yue_Hant", "ja": "jpn_Jpan", "ko": "kor_Hang",
    "vi": "vie_Latn", "fr": "fra_Latn", "de": "deu_Latn", "es": "spa_Latn", "pt": "por_Latn",
    "it": "ita_Latn", "ru": "rus_Cyrl", "uk": "ukr_Cyrl", "pl": "pol_Latn", "nl": "nld_Latn",
    "sv": "swe_Latn", "no": "nob_Latn", "nn": "nno_Latn", "da": "dan_Latn", "fi": "fin_Latn",
    "cs": "ces_Latn", "sk": "slk_Latn", "sl": "slv_Latn", "hu": "hun_Latn", "ro": "ron_Latn",
    "bg": "bul_Cyrl", "sr": "srp_Cyrl", "hr": "hrv_Latn", "bs": "bos_Latn", "mk": "mkd_Cyrl",
    "el": "ell_Grek", "tr": "tur_Latn", "ar": "arb_Arab", "fa": "pes_Arab", "he": "heb_Hebr",
    "hi": "hin_Deva", "bn": "ben_Beng", "ur": "urd_Arab", "ta": "tam_Taml", "te": "tel_Telu",
    "mr": "mar_Deva", "gu": "guj_Gujr", "kn": "kan_Knda", "ml": "mal_Mlym", "pa": "pan_Guru",
    "ne": "npi_Deva", "si": "sin_Sinh", "th": "tha_Thai", "lo": "lao_Laoo", "km": "khm_Khmr",
    "my": "mya_Mymr", "id": "ind_Latn", "ms": "zsm_Latn", "tl": "tgl_Latn", "jw": "jav_Latn",
    "su": "sun_Latn", "lt": "lit_Latn", "lv": "lvs_Latn", "et": "est_Latn", "ca": "cat_Latn",
    "gl": "glg_Latn", "eu": "eus_Latn", "be": "bel_Cyrl", "kk": "kaz_Cyrl", "uz": "uzn_Latn",
    "az": "azj_Latn", "ka": "kat_Geor", "hy": "hye_Armn", "mn": "khk_Cyrl", "sw": "swh_Latn",
    "af": "afr_Latn", "am": "amh_Ethi", "is": "isl_Latn", "ga": "gle_Latn", "cy": "cym_Latn",
}


def nllb_code(whisper_lang: str) -> str | None:
    return WHISPER_TO_NLLB.get(whisper_lang)


class Translator:
    def __init__(self, model_dir: Path, cpu_threads: int):
        self.model_dir = Path(model_dir)
        self.cpu_threads = cpu_threads
        self._model = None
        self._sp = None

    def load(self) -> None:
        import ctranslate2
        import sentencepiece

        self._model = ctranslate2.Translator(
            str(self.model_dir),
            device="cpu",
            compute_type="int8",
            inter_threads=1,
            intra_threads=self.cpu_threads,
        )
        self._sp = sentencepiece.SentencePieceProcessor(
            model_file=str(self.model_dir / "sentencepiece.bpe.model")
        )

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def translate(
        self,
        text: str,
        whisper_lang: str,
        target: str = "vi",
        beam_size: int = 2,
        repetition_penalty: float = 1.1,
    ) -> str | None:
        """Dịch ``text`` (mã ngôn ngữ Whisper) sang ``target`` (mặc định tiếng Việt).

        Trả về nguyên văn nếu cùng ngôn ngữ; ``None`` nếu không hỗ trợ ngôn ngữ. Giữ nguyên xuống dòng,
        mỗi câu được dịch riêng (NLLB được huấn luyện theo câu) trong một batch.
        """
        text = text.strip()
        if not text:
            return ""
        src, tgt = nllb_code(whisper_lang), nllb_code(target)
        if src is None or tgt is None:
            return None
        if src == tgt:
            return text
        if self._model is None:
            raise RuntimeError("Translator chưa được load()")

        lines = [split_sentences(line) for line in text.splitlines()]
        sentences = [s for line in lines for s in line]
        batch = [[src] + self._sp.encode(s, out_type=str) + ["</s>"] for s in sentences]
        results = self._model.translate_batch(
            batch,
            target_prefix=[[tgt]] * len(batch),
            beam_size=beam_size,
            max_batch_size=8,
            max_decoding_length=256,
            repetition_penalty=repetition_penalty,
        )
        outputs = iter(self._decode(r.hypotheses[0], tgt) for r in results)
        return "\n".join(" ".join(next(outputs) for _ in line) for line in lines).strip()

    def _decode(self, hyp: list[str], tgt: str) -> str:
        if hyp and hyp[0] == tgt:
            hyp = hyp[1:]
        return self._sp.decode(hyp).strip()


_SENTENCE_END = re.compile(r"(?<=[.!?…。！？])\s+")


def split_sentences(line: str) -> list[str]:
    return [s for s in (p.strip() for p in _SENTENCE_END.split(line)) if s]
