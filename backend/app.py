from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from chat_graph import build_chat_graph
from langchain_core.messages import HumanMessage, AIMessage
import os
import json
import logging
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
import hashlib
import requests
from bs4 import BeautifulSoup
from langchain_community.document_loaders import PyPDFLoader
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import os
import base64
import re
from langchain_community.document_loaders import RecursiveUrlLoader, UnstructuredURLLoader
from tavily import TavilyClient

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "false"

# Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret-key")
CORS(app, supports_credentials=True)

JSON_PATH = os.path.join(os.path.dirname(__file__), "restaurant-data.json")
PDF_PATH = os.path.join(os.path.dirname(__file__), "restaurant_menu.pdf")

# Load knowledge file
try:
    with open(JSON_PATH, "r") as f:
        knowledge = json.load(f)
except Exception as e:
    knowledge = {}
    logging.error("Failed to load knowledge base:", exc_info=e)

# --- Knowledge Embedding (with Cache) ---
FAISS_STORE_DIR = os.path.join(os.path.dirname(__file__), "faiss_store")
HASH_FILE_PATH = os.path.join(FAISS_STORE_DIR, "data.hash")

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def tavily_search(query: str):
    try:
        results = tavily.search(
            query=query,
            search_depth="advanced",
            max_results=3
        )
        if results and "results" in results:
            best = results["results"][0]
            return f"{best['title']}\n{best['url']}\n{best['content'][:400]}..."
        return ""
    except Exception as e:
        return ""

def json_to_documents(json_data: dict) -> list[Document]:
    documents = []
    for section, content in json_data.items():
        documents.append(
            Document(
                page_content=json.dumps({section: content}, indent=2),
                metadata={"source": "restaurant-data.json", "section": section},
            )
        )
    return documents

def scrape_website(url: str) -> list[Document]:
    def clean_content(html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Remove scripts, styles, nav, footer, header
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            return text
        except Exception:
            return ""

    def url_filter(url: str, visited: set) -> bool:
        if url in visited:
            return False
        exclude_patterns = [
            r".*\.(jpg|png|gif|jpeg|css|js|woff|woff2|ttf|ico|svg)$",
            r".*/(login|signup|admin|cart|checkout).*",
        ]
        return not any(re.match(pattern, url) for pattern in exclude_patterns)

    visited_urls = set()

    try:
        # Step 1: Crawl for URLs
        crawler = RecursiveUrlLoader(url=url, prevent_outside=False)
        pages = crawler.load()

        # Step 2: Filter URLs
        filtered_urls = []
        for page in pages:
            source_url = page.metadata.get("source", url)
            if url_filter(source_url, visited_urls):
                visited_urls.add(source_url)
                filtered_urls.append(source_url)

        # Step 3: Load cleaned content for filtered URLs
        loader = UnstructuredURLLoader(urls=filtered_urls, extractor=clean_content)
        raw_docs = loader.load()
        return [doc for doc in raw_docs if len(doc.page_content.strip()) > 50]

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []

def pdf_to_document(pdf_path: str) -> list[Document]:
    pdf_loader = PyPDFLoader(pdf_path)
    pages = pdf_loader.load()
    return pages

def get_file_hash(filepath):
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        logging.error("Error computing hash:", exc_info=e)
        return None

try:
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001", google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    current_hash = get_file_hash(JSON_PATH)
    stored_hash = None

    if os.path.exists(HASH_FILE_PATH):
        with open(HASH_FILE_PATH, "r") as f:
            stored_hash = f.read().strip()

    if current_hash != stored_hash or not os.path.exists(os.path.join(FAISS_STORE_DIR, "index.faiss")):
        logging.info("🔄 Rebuilding FAISS vector store...")
        documents = []
        documents.extend(json_to_documents(knowledge))
        documents.extend(scrape_website(os.getenv("SITE_URL")))
        documents.extend(pdf_to_document(PDF_PATH))
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
        chunks = text_splitter.split_documents(documents)
        vector_store = FAISS.from_documents(chunks, embeddings)
        vector_store.save_local(FAISS_STORE_DIR)

        os.makedirs(FAISS_STORE_DIR, exist_ok=True)
        with open(HASH_FILE_PATH, "w") as f:
            f.write(current_hash or "")
        logging.info("💾 FAISS vector store rebuilt and saved.")
    else:
        vector_store = FAISS.load_local(
            FAISS_STORE_DIR, embeddings, allow_dangerous_deserialization=True
        )
        logging.info("✅ Loaded FAISS vector store from disk.")

    retriever = vector_store.as_retriever(search_kwargs={"k": 5})

except Exception as e:
    retriever = None
    logging.error("Vector store setup failed:", exc_info=e)

# --- Knowledge Retrieval ---
def retrieve_knowledge(query: str) -> str:
    faiss_result = ""
    # tavily_result = ""

    try:
        docs_and_scores = vector_store.similarity_search_with_score(query, k=5)
        good_docs = [doc.page_content for doc, score in docs_and_scores if score > 0.7]
        if good_docs:
            faiss_result = "\n".join(good_docs)
    except Exception as e:
        logging.error("FAISS retrieval error", exc_info=e)

    try:
        tavily_result = tavily_search(query)
    except Exception as e:
        logging.error("Tavily search failed", exc_info=e)

    return (faiss_result + "\n\n" + tavily_result).strip()

# Build LangGraph once at startup
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
    user_lang = request.form.get("language", "en")

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

        knowledge_context = retrieve_knowledge(image_desc)

        # Final single Gemini call with both image details + context
        prompt_text = (
            "You are an assistant for ITC Narmada Hotel, Ahmedabad. "
            "Using the image details and hotel knowledge provided, "
            "give a short, accurate answer ONLY about this hotel. "
            "If unrelated, say: 'The image does not seem related to ITC Narmada Hotel.' "
            "Max 30 words, match user language.\n\n"
            f"(Note: Always respond in **{user_lang}** only. Never switch languages.)\n\n"
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
    user_lang = data.get("language", "en")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # Retrieve contextual knowledge
    knowledge_context = retrieve_knowledge(user_input)
    final_input = (
        f"{user_input}\n\n"
        f"(Note: Always respond in **{user_lang}** only. Never switch languages.)\n\n"
        "(Note: Wrap responses in HTML tags (<div>, <p>, <li>, etc.) but do not include <html> or triple backticks (```).)"
        f"Context (if any):\n{knowledge_context}"
    )

    messages = [HumanMessage(content=final_input)]

    try:
        result = graph.invoke({"messages": messages})
    except Exception as e:
        logging.error("LangGraph invocation failed:", exc_info=e)
        return jsonify({"response": "Something went wrong with the chatbot."})

    response_text = ""
    if "messages" in result and result["messages"]:
        last_msg = result["messages"][-1]
        if hasattr(last_msg, "content"):
            response_text = last_msg.content
        elif isinstance(last_msg, dict):
            response_text = last_msg.get("output", "")
        else:
            response_text = str(last_msg)

    return jsonify({"response": response_text, "language": user_lang})


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

    user_lang = request.form.get("language", "en")

    try:
        audio_file = request.files["audio"]
        url = "https://api.elevenlabs.io/v1/speech-to-text"

        headers = {"xi-api-key": ELEVEN_API_KEY}
        data = {
            "model_id": STT_MODEL_ID,
            "language": user_lang 
        }

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
        return jsonify({"transcript": transcript, "language": user_lang})

    except Exception as e:
        logging.error("STT error:", exc_info=e)
        return jsonify({"error": str(e)}), 500

@app.route("/tts", methods=["POST"])
def tts():
    if not ELEVEN_API_KEY or not VOICE_ID:
        return jsonify({"error": "Missing ELEVEN_API_KEY or ELEVEN_VOICE_ID"}), 500

    data = request.get_json()
    text = data.get("text", "").strip()
    user_lang = data.get("language", "en")  # From frontend

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
        payload = {
            "text": text,
            "model_id": TTS_MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            "language": user_lang  # Ensure TTS uses the selected language
        }
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