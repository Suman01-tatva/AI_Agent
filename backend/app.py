from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from chat_graph import build_chat_graph
from langchain_core.messages import HumanMessage , AIMessage , SystemMessage
import os
import json
import logging
import re
from io import BytesIO
from PIL import Image
from werkzeug.utils import secure_filename
import google.generativeai as genai
from langgraph.checkpoint.memory import MemorySaver
from knowledge_base import retriever_tool
from history_manager import add_message, get_user_history
import easyocr
reader = easyocr.Reader(['en'])
import numpy as np
import cv2

load_dotenv()
os.environ["LANGCHAIN_TRACING_V2"] = "false"

# Flask app setup
app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "http://localhost:5173"}},
    supports_credentials=True,
)

# --- LangGraph ---
memory_saver = MemorySaver()
graph = build_chat_graph()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- Utils ---
def compress_image(file, target_quality=85, max_size=(1024, 1024)):
    img = Image.open(file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail(max_size)
    img_bytes_io = BytesIO()
    img.save(img_bytes_io, format="JPEG", quality=target_quality, optimize=True)
    img_bytes_io.seek(0)
    return img_bytes_io.read(), "image/jpeg"

@app.route("/chat", methods=["POST"])
def chat():
    if graph is None:
        return jsonify({"response": "Chatbot is not available at the moment."}), 500

    data = request.get_json()
    user_input = data.get("message", "").strip()
    user_lang = data.get("language", "en")
    user_id = data.get("user_id", "default")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # --- Otherwise run LangGraph ---
    past_messages = [
        HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
        for msg in get_user_history(user_id)
    ]
    
    system_instruction = SystemMessage(
        content=f"Always respond in {'Hindi' if user_lang == 'hi' else 'Gujarati' if user_lang == 'gu' else 'English'}."
    )

    state = {"messages": [system_instruction] + past_messages + [HumanMessage(content=user_input)]}
    config = {"configurable": {"thread_id": user_id}}

    try:
        result = graph.invoke(state, config=config)
    except Exception as e:
        logging.error("LangGraph invocation failed:", exc_info=e)
        return jsonify({"response": "Something went wrong with the chatbot."}), 500

    final_response = result["messages"][-1].content.strip()

    # --- Normal case ---
    add_message(user_id, "user", user_input)

    return jsonify({"response": final_response, "language": user_lang})

def analyze_image_custom(image_bytes: bytes) -> str:
    np_img = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    results = reader.readtext(img)
    text = " ".join([res[1] for res in results])
    return text if text else "No text found"

from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image

processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

def generate_caption(image_bytes: bytes) -> str:
    img = Image.open(BytesIO(image_bytes))
    inputs = processor(img, return_tensors="pt")
    out = model.generate(**inputs, max_length=30)
    return processor.decode(out[0], skip_special_tokens=True)

def process_image_for_llm(image_bytes: bytes) -> str:
    ocr_text = analyze_image_custom(image_bytes)
    caption = generate_caption(image_bytes)

    combined = f"OCR text: {ocr_text}\nImage caption: {caption}"
    return combined


# --- Translation Helper ---
def translate_to_language(html_text: str, lang: str) -> str:
    """Translate DuckDuckGo results into Hindi/Gujarati/English while preserving HTML tags."""
    if lang == "en":  # no translation needed
        return html_text

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Translate the following text into "
            f"{'Hindi' if lang == 'hi' else 'Gujarati'} "
            f"but KEEP all HTML tags exactly as they are:\n\n{html_text}"
        )
        response = model.generate_content(prompt)
        return response.text.strip() if response and response.text else html_text
    except Exception as e:
        logging.error(f"Translation failed: {e}")
        return html_text


@app.route("/image-chat", methods=["POST"])
def image_chat():
    if "image" not in request.files:
        return jsonify({"error": "❗ No image file provided"}), 400

    image_file = request.files["image"]
    filename = secure_filename(image_file.filename)
    user_id = request.form.get("user_id", "default")
    user_language = request.form.get("language", "en")  # ✅ allow passing language here

    try:
        compressed_bytes, mime_type = compress_image(image_file)

        image_desc = process_image_for_llm(compressed_bytes)
        knowledge_context = retriever_tool.invoke(image_desc)

        # Step 3: Run through LangGraph
        prompt_text = (
            "You are an assistant for ITC Narmada Hotel, Ahmedabad. "
            "Using the image details and hotel knowledge provided, "
            "give a short, accurate answer ONLY about this hotel. "
            "If unrelated, say: 'The image does not seem related to ITC Narmada Hotel.' "
            "Max 30 words, match user language.\n\n"
            f"(Note: Always respond in {'Hindi' if user_language == 'hi' else 'Gujarati' if user_language == 'gu' else 'English'}.)\n\n"
            f"Image details: {image_desc}\n"
            f"Hotel knowledge: {knowledge_context}"
        )

        config = {"configurable": {"thread_id": user_id}}
        result = graph.invoke({"messages": [HumanMessage(content=prompt_text)]}, config)

        return jsonify({"response": result["messages"][-1].content})

    except Exception as e:
        logging.error("Image-chat failed:", exc_info=e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
