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

# Load environment variables
load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "false"

# Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret-key")
CORS(app, supports_credentials=True)

# Load knowledge file
try:
    with open("restaurant-data.json", "r") as f:
        knowledge = json.load(f)
except Exception as e:
    knowledge = {}
    logging.error("Failed to load knowledge base:", exc_info=e)

# --- Knowledge Embedding (with Cache) ---
FAISS_STORE_DIR = "faiss_store"
HASH_FILE_PATH = os.path.join(FAISS_STORE_DIR, "data.hash")
JSON_PATH = "restaurant-data.json"

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

def scrape_website(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text()
    return text

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
        documents = json_to_documents(knowledge)
        scraped_text = scrape_website(os.getenv("SITE_URL"))
        scraped_doc = Document(
            page_content=scraped_text,
            metadata={"source": "itchotels.com", "type": "scraped"}
        )
        documents.append(scraped_doc)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
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

    retriever = vector_store.as_retriever(search_kwargs={"k": 3})

except Exception as e:
    retriever = None
    logging.error("Vector store setup failed:", exc_info=e)

# --- Knowledge Retrieval ---
def retrieve_knowledge(query: str) -> str:
    try:
        docs = retriever.invoke(query) if retriever else []
        return "\n".join([doc.page_content for doc in docs]) if docs else ""
    except Exception as e:
        logging.error("Knowledge retrieval error:", exc_info=e)
        return ""

# Build LangGraph once at startup
graph = build_chat_graph()

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_input = data.get("message", "").strip()

    if not user_input:
        return jsonify({"error": "❗ No message provided"}), 400

    # Inject knowledge into latest human input
    knowledge_context = retrieve_knowledge(user_input)
    final_input = (
        f"{user_input}\n\n"
        f"(Note: Always respond in the **same language** as the user.)\n\n"
        f"Context (if any):\n{knowledge_context}"
    )

    # Create LangChain message list with one HumanMessage
    messages = [HumanMessage(content=final_input)]

    # Invoke LangGraph
    try:
        result = graph.invoke({"messages": messages})
    except Exception as e:
        logging.error("LangGraph invocation failed:", exc_info=e)
        return jsonify({"response": "❌ Something went wrong with the chatbot."})

    # Extract response
    last_msg = result["messages"][-1]
    if isinstance(last_msg, dict) and "output" in last_msg:
        response_text = last_msg["output"]
    elif hasattr(last_msg, "content"):
        response_text = last_msg.content
    else:
        response_text = str(last_msg)

    return jsonify({"response": response_text})

if __name__ == "__main__":
    app.run(debug=True)