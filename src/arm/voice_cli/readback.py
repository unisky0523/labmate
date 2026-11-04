"""Choose a local text readback implementation for PC or board."""

import platform


def speak_text(text):
    if platform.system() == "Windows":
        from pc_speaker import speak_text as implementation
    else:
        from board_speaker import speak_text as implementation
    return implementation(text)
