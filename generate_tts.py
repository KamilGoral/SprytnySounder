#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt do generowania komunikatów Recyklomat przez ElevenLabs.
Uruchom po ustawieniu ELEVENLABS_API_KEY i VOICE_ID.

Usage:
    set ELEVENLABS_API_KEY=sk_...
    set VOICE_ID=nPczCjzI2devNBz1zQrb    # <- podstaw swój voice_id
    python generate_tts.py
"""

import os, sys, json
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
VOICE_ID = os.getenv("VOICE_ID", "nPczCjzI2devNBz1zQrb")  # <- ZMIEŃ na swój głos
OUTPUT_DIR = "static/sounds"

MESSAGES = {
    "recyklomat-oproznij.mp3": (
        "Uwaga! Ktoś musi podejść do recyklomatu i wymienić kosze, "
        "bo są pełne butelek i puszek."
    ),
    "recyklomat-pomoc.mp3": (
        "Uwaga! Potrzebna pomoc przy recyklomacie. "
        "Ktoś z sali sprzedaży proszony o podejście do klienta."
    ),
}

def main():
    if not API_KEY:
        print("❌ Ustaw zmienną ELEVENLABS_API_KEY")
        print("   set ELEVENLABS_API_KEY=sk_...")
        sys.exit(1)

    client = ElevenLabs(api_key=API_KEY)

    # Sprawdź dostępne głosy
    voices = client.voices.get_all()
    print(f"Dostępne głosy ({len(voices.voices)}):")
    for v in voices.voices:
        if "pol" in v.name.lower() or "pol" in (v.labels or {}).get("accent", "").lower():
            print(f"  • {v.voice_id}: {v.name} (Polish?)")
    print(f"\nUżyję voice_id: {VOICE_ID}")
    print()

    for filename, text in MESSAGES.items():
        print(f"Generuję {filename}...")
        response = client.text_to_speech.convert(
            voice_id=VOICE_ID,
            output_format="mp3_44100_128",
            text=text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.40,
                similarity_boost=0.75,
                style=0.70,
                use_speaker_boost=True,
            ),
        )

        # Zapisz MP3
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, filename)
        with open(output_path, "wb") as f:
            for chunk in response:
                f.write(chunk)

        size_kb = os.path.getsize(output_path) / 1024
        print(f"  ✅ Zapisano: {output_path} ({size_kb:.1f} KB)")

    print("\n✅ Gotowe! Oba pliki MP3 są gotowe do użycia.")
    print("   Panel HTML już ma przyciski dla tych plików.")


if __name__ == "__main__":
    main()
