"""Select the official Vosk package or the minimal libvosk loader."""

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel  # type: ignore
    BACKEND = "vosk"
    IMPORT_ERROR = None
except Exception as error:
    from vosk_lite import Model, KaldiRecognizer, SetLogLevel  # type: ignore
    BACKEND = "vosk_lite"
    IMPORT_ERROR = error
