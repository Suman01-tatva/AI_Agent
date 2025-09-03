from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import numpy as np
import re
import logging
import cv2
import easyocr
reader = easyocr.Reader(
    ['en'],
    model_storage_directory="D:/Project/chatbot_final/AI_Agent/backend/models/easyocr"
)
from faster_whisper import WhisperModel
import google.generativeai as google_genai
from langchain_core.messages import HumanMessage, AIMessage
from io import BytesIO
from PIL import Image
import base64

from google import genai
from google.genai import types
import wave
import io
import tempfile
from knowledge_base import knowledge_retriever_tool
 
# ---------- Load env ----------
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("Set GOOGLE_API_KEY in .env or environment variables.")

# ---------- Config ----------
os.environ["LANGCHAIN_TRACING_V2"] = "false"

WHISPER_MODEL = "large-v3-turbo"
WHISPER_COMPUTE_TYPE = "int8"  # float32, float16, int8_float16, int8
TTS_MODEL_NAME = "models/gemini-2.5-flash-preview-tts"
LLM_MODEL = "models/gemini-2.5-flash"

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("ELEVEN_VOICE_ID")
TTS_MODEL_ID = "eleven_multilingual_v2" 
STT_MODEL_ID = "scribe_v1"

# Flask app setup
app = Flask(__name__,static_folder="dist")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret-key")
# CORS(app, origins=["http://localhost:5173"], supports_credentials=True)
CORS(app, resources={r"/*": {"origins": "*"}})

whisperModel = WhisperModel(WHISPER_MODEL, compute_type=WHISPER_COMPUTE_TYPE)
client = genai.Client()

# Build LangGraph once at startup
from knowledge_base import knowledge_retriever_tool,add_to_knowledge_base
from chat_graph import build_chat_graph
graph = build_chat_graph()

google_genai.configure(api_key=GOOGLE_API_KEY)

# --- Image compression and chat ---
def compress_image(file, target_quality=85, max_size=(1024, 1024)):
    try:
        img = Image.open(file)

        # Convert RGBA → RGB (JPEG doesn't support alpha)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize if needed (keep aspect ratio)
        img.thumbnail(max_size)

        img_bytes_io = BytesIO()
        img.save(img_bytes_io, format="JPEG", quality=target_quality, optimize=True)
        img_bytes_io.seek(0)

        return img_bytes_io.read(), "image/jpeg"

    except Exception as e:
        raise ValueError(f"Image compression failed: {str(e)}")

def analyze_image_custom(image_bytes: bytes) -> str:
    np_img = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    results = reader.readtext(img)
    text = " ".join([res[1] for res in results])
    return text if text else "No text found"

from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image

processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-large") # blip-image-captioning-base,blip-image-captioning-large,blip2-opt-2.7b
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-large")

def generate_caption(image_bytes: bytes) -> str:
    img = Image.open(BytesIO(image_bytes))
    inputs = processor(img, return_tensors="pt")
    out = model.generate(**inputs, max_new_tokens=50)
    return processor.decode(out[0], skip_special_tokens=True)

def process_image_for_llm(image_bytes: bytes) -> str:
    ocr_text = analyze_image_custom(image_bytes)
    caption = generate_caption(image_bytes)

    combined = f"OCR text: {ocr_text}\nImage caption: {caption}"
    return combined

@app.route("/image-chat", methods=["POST"])
def image_chat():
    if "file" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    image_file = request.files.get("file")
    user_input = request.form.get("question", "").strip()
    thread_id = request.form.get("thread_id", "").strip()
    try:
        compressed_bytes, mime_type = compress_image(image_file)
        image_desc = process_image_for_llm(compressed_bytes)
        knowledge_context = knowledge_retriever_tool.invoke(image_desc)

        # Step 3: Run through LangGraph
        prompt_text = (
            "Using the image details and hotel knowledge provided, answer user querys."
            "give a short, accurate answer."
            "match user language.\n\n"
            f"Image details: {image_desc}\n"
            f"Hotel knowledge: {knowledge_context}"
            f"User question: {user_input}"
            "Always try to frame a proper answer."
        )

        config = {"configurable": {"thread_id": {thread_id}}}
        result = graph.invoke(
            {"messages": [HumanMessage(content=prompt_text)]},
            config=config
        )

        response_text = result["messages"][-1].content
        
        return jsonify({"response": response_text})
    except Exception as e:
            logging.error("Image-chat failed:", exc_info=e)
            return jsonify({"error": str(e)}), 500

# --- Text chat ---
@app.route("/chat", methods=["POST"])
def chat():
    if graph is None:
        return jsonify({"response": "Chatbot is not available at the moment."}), 500

    data = request.get_json()
    user_input = data.get("message", "").strip()
    thread_id = data.get("thread_id", "").strip()
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # Load previous state or initialize new
    config = {"configurable": {"thread_id": {thread_id}}}
    # previous_state = graph.get_state(config).values if graph.get_state(config) else {}
    # state = {
    #     "messages": previous_state.get("messages", []) + [HumanMessage(content=user_input)]
    # }
    # print("State messages:", [msg.content for msg in state["messages"]])
        
    try:
        # result = graph.invoke(state, config=config)
        result = graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config
        )
        print("Final messages:", [msg.content for msg in result["messages"]])
    except Exception as e:
        logging.error("LangGraph invocation failed:", exc_info=e)
        return jsonify({"response": "Something went wrong with the chatbot."})

    final_response = result["messages"][-1].content
    # --- Post-process: Remove Markdown/code fences and triple backticks ---
    if isinstance(final_response, str):
        final_response = re.sub(r"^```[a-zA-Z]*\s*", "", final_response.strip())  # remove ```html, ```markdown etc.
        final_response = re.sub(r"```$", "", final_response)  # remove trailing ``` 

    return jsonify({"response": final_response})

# --- STT and TTS with Elevenlabs ---
@app.route("/stt", methods=["POST"])
def stt():
    if not ELEVEN_API_KEY:
        return jsonify({"error": "Missing ELEVEN_API_KEY"}), 500

    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    user_lang = request.form.get("language")

    try:
        audio_file = request.files["audio"]
        url = "https://api.elevenlabs.io/v1/speech-to-text"

        headers = {"xi-api-key": ELEVEN_API_KEY}
        data = {
            "model_id": STT_MODEL_ID,
        }
        if user_lang:
            data["language_code"] = user_lang

        files = {"file": (audio_file.filename, audio_file.stream, audio_file.mimetype)}

        response = requests.post(url, headers=headers, data=data, files=files)

        if response.status_code != 200:
            try:
                err_msg = response.json().get("detail", {}).get("message", "")
            except Exception:
                err_msg = response.text
            logging.error(f"STT API error {response.status_code}: {err_msg}")
            return (
                jsonify({"error": err_msg or f"STT API error {response.status_code}"}),
                500,
            )

        result = response.json()
        transcript = result.get("text", "").strip()
        return jsonify({"transcript": transcript})

    except Exception as e:
        logging.error("STT error:", exc_info=e)
        return jsonify({"error": str(e)}), 500

@app.route("/tts", methods=["POST"])
def tts():
    if not ELEVEN_API_KEY or not VOICE_ID:
        return jsonify({"error": "Missing ELEVEN_API_KEY or ELEVEN_VOICE_ID"}), 500

    data = request.get_json()
    text = data.get("text", "").strip()
    user_lang = data.get("language")  # From frontend

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
        payload = {
            "text": text,
            "model_id": TTS_MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        if user_lang:
            payload["language_code"] = user_lang
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVEN_API_KEY,
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            try:
                err_msg = response.json().get("detail", {}).get("message", "")
            except Exception:
                err_msg = response.text
            logging.error(f"TTS API error {response.status_code}: {err_msg}")
            return (
                jsonify({"error": err_msg or f"TTS API error {response.status_code}"}),
                500,
            )

        audio_base64 = base64.b64encode(response.content).decode("utf-8")
        return jsonify({"audio": audio_base64, "language": user_lang})

    except Exception as e:
        logging.error("TTS error:", exc_info=e)
        return jsonify({"error": str(e)}), 500

# --- STT with Whisper ---
@app.route("/whisper-stt", methods=["POST"])
def whisperstt():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    audio_file = request.files["audio"]

    # Save temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        audio_file.save(tmp.name)
        temp_path = tmp.name

    try:
        # Transcribe
        user_lang = request.form.get("language") or None
        segments, info = whisperModel.transcribe(temp_path,language = user_lang, task="transcribe", beam_size=7, condition_on_previous_text=True,word_timestamps=False, temperature=[0.0, 0.2, 0.4])
        text = " ".join([s.text.strip() for s in segments])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.remove(temp_path)

    return jsonify({"transcript": text,"language": info.language})

# --- TTS with Gemini ---
@app.route("/gemini-tts", methods=["POST"])
def synthesize_tts():
    """
    Returns base64-encoded audio (string).
    """
    data = request.get_json()
    text = data.get("text", "").strip()
    user_lang = data.get("language")  # From frontend
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        response = client.models.generate_content(
            model=TTS_MODEL_NAME,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    language_code=user_lang
                )
            )
        )
        data = response.candidates[0].content.parts[0].inline_data.data
        voice = pcm_to_wav_base64(data)
        return jsonify({"audio": voice, "language": user_lang}), 200
    except Exception as e:
        raise RuntimeError(f"TTS synthesis failed: {e}")

def pcm_to_wav_base64(pcm_bytes: bytes, channels=1, rate=24000, sample_width=2) -> str:
    """
    Convert raw PCM16 bytes into WAV base64 string for frontend playback.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)      # mono
        wf.setsampwidth(sample_width)  # 16-bit
        wf.setframerate(rate)          # 24 kHz
        wf.writeframes(pcm_bytes)

    wav_bytes = buffer.getvalue()
    return base64.b64encode(wav_bytes).decode("utf-8")
    
# --- Add documents to knowledge base ---
@app.route("/add-docs", methods=["POST"])
def add_docs():
    texts = request.form.getlist("texts")
    files = request.files.getlist("files")

    if not texts and not files:
        return jsonify({"detail": "Provide text or files (JSON, PDF, DOCX)."}), 400

    return add_to_knowledge_base(texts, files)

# --- Gemini image + text chat ---
@app.route("/gemini-image-chat", methods=["POST"])
def vision_chat():
    try:
        question = request.form.get("question", "").strip()
        file = request.files.get("file")
        thread_id = request.form.get("thread_id", "").strip()
        if not question or not file:
            return jsonify({"detail": "Missing question or file"}), 400

        # Read uploaded file bytes
        content = file.read()

        # Run multimodal agent
        reply = run_agent_multimodal(question, content, thread_id)

    except Exception as e:
        return jsonify({"detail": f"Multimodal error: {e}"}), 500

    return jsonify({"response": reply})

def run_agent_multimodal(user_text: str, image_bytes: bytes , thread_id: str) -> str:
    """Send text + image (as bytes) to Google GenAI multimodal model."""

    # Default MIME type
    mime_type = "image/png"

    # Try to detect real format via Pillow
    try:
        img = Image.open(BytesIO(image_bytes))
        fmt = img.format.lower()
        if fmt in ["jpeg", "jpg"]:
            mime_type = "image/jpeg"
        elif fmt == "png":
            mime_type = "image/png"
        elif fmt == "webp":
            mime_type = "image/webp"
    except Exception:
        pass  # fallback stays "image/png"

    # Encode image as base64
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    config = {"configurable": {"thread_id": {thread_id}}}
    snapshot = graph.get_state(config)
    previous_state = snapshot.values if snapshot.values else {"messages": []}
    # Send multimodal request to Gemini
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(text=user_text),
                    types.Part(
                        inline_data=types.Blob(
                            mime_type=mime_type,
                            data=b64_img
                        )
                    ),
                ],
            )
        ]
    )
    final_response = response.candidates[0].content.parts[0].text
    new_messages = previous_state["messages"] + [
        HumanMessage(content=user_text+"\n Image : {b64_img}"),
        AIMessage(content=final_response)
    ]
    graph.update_state(config, {"messages": new_messages})
    # Return model’s text reply
    return final_response

@app.route("/widget.html")
def widget_page():
    return send_from_directory(app.static_folder, "index.html")

# Serve assets (css/js/images)
@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(f"{app.static_folder}/assets", filename)

@app.route("/")
def hello():
    return jsonify({"status": "ok", "message": "Flask backend is running."})

application = app

# if __name__ == "__main__":
#     app.run(debug=True,port=5001)