"""
Omnipect Voice Agent Demonstration Tool
Tests the full Voice Agent Pipeline:
Microphone / Audio Input -> STT (Faster-Whisper) -> Nemotron LLM (Industrial Tools) -> TTS (Edge-TTS) -> Speaker Playback
"""
import io
import sys
import time
import wave
import base64
import requests
import sounddevice as sd
import numpy as np
import winsound

BACKEND_URL = "http://127.0.0.1:8080/api/v1/voice"
SAMPLE_RATE = 16000

def check_backend():
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=3)
        if r.status_code == 200:
            data = r.json()
            print("=" * 65)
            print("  Omnipect Voice Agent Pipeline: ONLINE")
            print(f"  * LLM Model   : {data.get('model')}")
            print(f"  * STT Engine  : faster-whisper ({data.get('stt_model')})")
            print(f"  * TTS Voice   : {data.get('tts_voice')}")
            print("=" * 65)
            return True
    except Exception as e:
        print(f"[ERROR] Cannot connect to Omnipect Backend at {BACKEND_URL}")
        print("Please make sure the backend is running (run Start_Omnipect.bat).")
        return False
    return False

def record_audio(duration=4):
    print(f"\n[*] Recording for {duration} seconds... SPEAK NOW! (e.g. 'What is the health of motor one?')")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    for remaining in range(duration, 0, -1):
        print(f"    Recording... {remaining}s remaining", end="\r")
        time.sleep(1)
    sd.wait()
    print("    Recording complete! Processing...          ")
    
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()

def send_to_voice_agent(wav_bytes):
    print("[*] Sending audio to STT -> Nemotron LLM -> TTS pipeline...")
    t0 = time.time()
    try:
        resp = requests.post(
            f"{BACKEND_URL}/chat/json",
            data=wav_bytes,
            headers={"Content-Type": "audio/wav", "X-Session-Id": "demo"},
            timeout=30
        )
        elapsed = time.time() - t0
        if resp.status_code != 200:
            print(f"[!] Server returned error {resp.status_code}: {resp.text}")
            return
            
        data = resp.json()
        print("\n" + "-" * 65)
        print(f"🎤 USER SAID    : \"{data.get('transcript', '')}\"")
        print(f"🤖 OMNIPECT AI  : \"{data.get('text', '')}\"")
        if data.get('tool_calls'):
            print(f"⚙️ TOOLS CALLED : {data.get('tool_calls')}")
        print(f"⏱️ TOTAL LATENCY: {elapsed:.2f} seconds")
        print("-" * 65)
        
        # Play the synthesized voice audio through speakers
        b64 = data.get("audio_base64")
        if b64:
            reply_wav = base64.b64decode(b64)
            with open("demo_reply.wav", "wb") as f:
                f.write(reply_wav)
            print("🔊 PLAYING SPOKEN RESPONSE THROUGH SPEAKERS...")
            winsound.PlaySound("demo_reply.wav", winsound.SND_FILENAME)
            print("✔ Playback finished.")
        else:
            print("[!] No audio returned in response.")
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")

def text_to_speech_demo(text_query):
    print(f"\n[*] Simulating voice question: \"{text_query}\"")
    # Generate synthetic speech for the question or synthesize via TTS directly
    try:
        # First use backend TTS to generate the question audio
        tts_resp = requests.post(
            f"{BACKEND_URL}/tts",
            json={"text": text_query, "voice": "en-US-GuyNeural"},
            timeout=15
        )
        if tts_resp.status_code == 200:
            send_to_voice_agent(tts_resp.content)
        else:
            print("[!] Could not generate question audio.")
    except Exception as e:
        print(f"[ERROR] {e}")

def main():
    if not check_backend():
        sys.exit(1)
        
    print("\nDemonstration Menu:")
    print("1. Speak into PC Microphone (Full Mic -> STT -> LLM -> TTS -> Speaker)")
    print("2. Quick Demo: Ask 'What is the health of motor one?' (Audio -> LLM -> Speaker)")
    print("3. Quick Demo: Ask 'Are there any bearing faults detected?' (Audio -> LLM -> Speaker)")
    print("4. Quick Demo: Ask 'How is my CPU and GPU performing?' (Audio -> LLM -> Speaker)")
    print("5. Type your own question (Simulate voice question)")
    print("q. Quit")
    
    while True:
        choice = input("\nSelect option [1-5, q]: ").strip().lower()
        if choice == '1':
            wav = record_audio(duration=4)
            send_to_voice_agent(wav)
        elif choice == '2':
            text_to_speech_demo("What is the health of motor one?")
        elif choice == '3':
            text_to_speech_demo("Are there any bearing faults detected on the machinery?")
        elif choice == '4':
            text_to_speech_demo("How is my CPU and GPU performing?")
        elif choice == '5':
            q = input("Enter your question: ").strip()
            if q:
                text_to_speech_demo(q)
        elif choice == 'q':
            print("Exiting demonstration.")
            break

if __name__ == "__main__":
    main()
