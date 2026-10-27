"""The Whisper model used for transcripts and language detection: on the GPU when CUDA is available, else on the CPU."""
import ctranslate2
from faster_whisper import WhisperModel

GPU = ctranslate2.get_cuda_device_count() > 0


def load():
    return WhisperModel("large-v3-turbo", device="cuda" if GPU else "cpu", compute_type="float16" if GPU else "int8")
