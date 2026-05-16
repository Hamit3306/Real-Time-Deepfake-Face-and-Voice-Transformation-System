import librosa
import soundfile as sf
import sys

try:
    y, sr = librosa.load("references/zeki_muren.wav", sr=None)
    y_fast = librosa.effects.time_stretch(y, rate=1.5)
    y_pitched = librosa.effects.pitch_shift(y, sr=sr, n_steps=2)
    print("Librosa effects work!")
except Exception as e:
    print("Error:", e)
    sys.exit(1)
