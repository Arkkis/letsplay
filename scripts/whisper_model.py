"""The Whisper model used for transcripts and language detection: on the GPU when CUDA is available, else on the CPU.
config "whisper_model" picks the model (default large-v3: noticeably better than large-v3-turbo on colloquial speech)."""
import os, sys
import ctranslate2
from faster_whisper import WhisperModel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import CFG

GPU = ctranslate2.get_cuda_device_count() > 0


def load():
    return WhisperModel(CFG.get("whisper_model", "large-v3"), device="cuda" if GPU else "cpu", compute_type="float16" if GPU else "int8")
