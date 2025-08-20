from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
import os
import logging
import requests
from werkzeug.utils import secure_filename
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import os
import base64
import re

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "false"

# Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret-key")
CORS(app, supports_credentials=True)

# Build LangGraph once at startup
from knowledge_base import retriever_tool
from chat_graph import build_chat_graph
graph = build_chat_graph()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

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

@app.route("/image-chat", methods=["POST"])
def image_chat():
    if "image" not in request.files:
        return jsonify({"error": "❗ No image file provided"}), 400

    image_file = request.files["image"]
    filename = secure_filename(image_file.filename)

    try:
        # Compress image
        compressed_bytes, mime_type = compress_image(image_file)

        model = genai.GenerativeModel("gemini-1.5-flash")
        image_desc = model.generate_content([
            "Briefly describe the key elements of this image (50 words).",
            {
                "mime_type": mime_type,
                "data": compressed_bytes
            }
        ]).text.strip()

        knowledge_context = retriever_tool.invoke(image_desc)

        # Final single Gemini call with both image details + context
        prompt_text = (
            "You are an assistant for ITC Narmada Hotel, Ahmedabad. "
            "Using the image details and hotel knowledge provided, "
            "give a short, accurate answer ONLY about this hotel. "
            "If unrelated, say: 'The image does not seem related to ITC Narmada Hotel.' "
            "Max 30 words, match user language.\n\n"
            f"(Note: Always respond in user's input language.)\n\n"
            f"Image details: {image_desc}\n"
            f"Hotel knowledge: {knowledge_context}"
        )

        final_response = model.generate_content(prompt_text)

        return jsonify({"response": final_response.text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/chat", methods=["POST"])
def chat():
    if graph is None:
        return jsonify({"response": "Chatbot is not available at the moment."}), 500

    data = request.get_json()
    user_input = data.get("message", "").strip()

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # Load previous state or initialize new
    config = {"configurable": {"thread_id": "default"}}
    previous_state = graph.get_state(config).values if graph.get_state(config) else {}
    state = {
        "messages": previous_state.get("messages", []) + [HumanMessage(content=user_input)]
    }
    print("State messages:", [msg.content for msg in state["messages"]])
        
    try:
        result = graph.invoke(state, config=config)
    except Exception as e:
        logging.error("LangGraph invocation failed:", exc_info=e)
        return jsonify({"response": "Something went wrong with the chatbot."})

    final_response = result["messages"][-1].content
    # --- Post-process: Remove Markdown/code fences and triple backticks ---
    if isinstance(final_response, str):
        final_response = re.sub(r"^```[a-zA-Z]*\s*", "", final_response.strip())  # remove ```html, ```markdown etc.
        final_response = re.sub(r"```$", "", final_response)  # remove trailing ``` 

    return jsonify({"response": final_response})


ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("ELEVEN_VOICE_ID")

TTS_MODEL_ID = "eleven_multilingual_v2" 
STT_MODEL_ID = "scribe_v1"

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

if __name__ == "__main__":
    app.run(debug=True)