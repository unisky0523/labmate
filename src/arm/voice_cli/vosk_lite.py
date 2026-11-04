"""Minimal ARMv7 Vosk loader using the official libvosk.so.

This avoids requiring the full ``vosk`` Python package and its optional
transcriber dependencies (requests, tqdm, srt, websockets).
"""

import ctypes
from pathlib import Path


BACKEND = "vosk_lite"
_LIBRARY = None


def _library_path():
    return Path(__file__).resolve().parent / "libvosk.so"


def _load_library():
    global _LIBRARY
    if _LIBRARY is not None:
        return _LIBRARY
    path = _library_path()
    if not path.is_file():
        raise OSError("找不到 libvosk.so：%s" % path)
    local_atomic = Path(__file__).resolve().parent / "lib" / "libatomic.so.1"
    if local_atomic.is_file():
        try:
            ctypes.CDLL(str(local_atomic), mode=getattr(ctypes, "RTLD_GLOBAL", 0))
        except OSError:
            pass
    library = ctypes.CDLL(str(path))
    library.vosk_model_new.argtypes = [ctypes.c_char_p]
    library.vosk_model_new.restype = ctypes.c_void_p
    library.vosk_model_free.argtypes = [ctypes.c_void_p]
    library.vosk_model_free.restype = None
    library.vosk_recognizer_new.argtypes = [ctypes.c_void_p, ctypes.c_float]
    library.vosk_recognizer_new.restype = ctypes.c_void_p
    library.vosk_recognizer_new_grm.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_char_p]
    library.vosk_recognizer_new_grm.restype = ctypes.c_void_p
    library.vosk_recognizer_free.argtypes = [ctypes.c_void_p]
    library.vosk_recognizer_free.restype = None
    library.vosk_recognizer_set_words.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.vosk_recognizer_set_words.restype = None
    library.vosk_recognizer_set_grm.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    library.vosk_recognizer_set_grm.restype = None
    library.vosk_recognizer_accept_waveform.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    library.vosk_recognizer_accept_waveform.restype = ctypes.c_int
    library.vosk_recognizer_result.argtypes = [ctypes.c_void_p]
    library.vosk_recognizer_result.restype = ctypes.c_char_p
    library.vosk_recognizer_partial_result.argtypes = [ctypes.c_void_p]
    library.vosk_recognizer_partial_result.restype = ctypes.c_char_p
    library.vosk_recognizer_final_result.argtypes = [ctypes.c_void_p]
    library.vosk_recognizer_final_result.restype = ctypes.c_char_p
    library.vosk_recognizer_reset.argtypes = [ctypes.c_void_p]
    library.vosk_recognizer_reset.restype = None
    library.vosk_set_log_level.argtypes = [ctypes.c_int]
    library.vosk_set_log_level.restype = None
    _LIBRARY = library
    return library


def _text(value):
    if not value:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return ctypes.string_at(value).decode("utf-8", "replace")


class Model:
    def __init__(self, model_path=None, model_name=None, lang=None):
        if model_path is None:
            raise ValueError("vosk_lite 需要显式模型路径。")
        self._library = _load_library()
        self._handle = self._library.vosk_model_new(str(model_path).encode("utf-8"))
        if not self._handle:
            raise RuntimeError("无法加载 Vosk 模型：%s" % model_path)

    def __del__(self):
        handle = getattr(self, "_handle", None)
        if handle:
            try:
                self._library.vosk_model_free(handle)
            except Exception:
                pass
            self._handle = None


class KaldiRecognizer:
    def __init__(self, *args):
        self._library = _load_library()
        # Keep native model data alive for the recognizer's whole lifetime.
        self._model = args[0] if args else None
        if len(args) == 2:
            model, sample_rate = args
            self._handle = self._library.vosk_recognizer_new(
                model._handle, ctypes.c_float(float(sample_rate)))
        elif len(args) == 3 and isinstance(args[2], str):
            model, sample_rate, grammar = args
            self._handle = self._library.vosk_recognizer_new_grm(
                model._handle, ctypes.c_float(float(sample_rate)), grammar.encode("utf-8"))
        else:
            raise TypeError("不支持的 KaldiRecognizer 参数。")
        if not self._handle:
            raise RuntimeError("无法创建 Vosk recognizer。")

    def __del__(self):
        handle = getattr(self, "_handle", None)
        if handle:
            try:
                self._library.vosk_recognizer_free(handle)
            except Exception:
                pass
            self._handle = None

    def SetWords(self, enable_words):
        self._library.vosk_recognizer_set_words(self._handle, 1 if enable_words else 0)

    def SetGrammar(self, grammar):
        self._library.vosk_recognizer_set_grm(self._handle, grammar.encode("utf-8"))

    def AcceptWaveform(self, data):
        result = self._library.vosk_recognizer_accept_waveform(self._handle, data, len(data))
        if result < 0:
            raise RuntimeError("Vosk 处理音频失败。")
        return result

    def Result(self):
        return _text(self._library.vosk_recognizer_result(self._handle))

    def PartialResult(self):
        return _text(self._library.vosk_recognizer_partial_result(self._handle))

    def FinalResult(self):
        return _text(self._library.vosk_recognizer_final_result(self._handle))

    def Reset(self):
        return self._library.vosk_recognizer_reset(self._handle)


def SetLogLevel(level):
    return _load_library().vosk_set_log_level(int(level))
