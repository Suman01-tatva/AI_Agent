from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from bs4 import BeautifulSoup
import hashlib
import json
from langchain_community.document_loaders import RecursiveUrlLoader, UnstructuredURLLoader
import re
import os
import logging
import asyncio
from websearch import custom_web_search

JSON_PATH = os.path.join(os.path.dirname(__file__), "restaurant-data.json")
PDF_PATH = os.path.join(os.path.dirname(__file__), "restaurant_menu.pdf")

# --- Knowledge Embedding (with Cache) ---
FAISS_STORE_DIR = os.path.join(os.path.dirname(__file__), "faiss_store")
HASH_FILE_PATH = os.path.join(FAISS_STORE_DIR, "data.hash")

# Load knowledge file
try:
    with open(JSON_PATH, "r") as f:
        knowledge = json.load(f)
except Exception as e:
    knowledge = {}
    logging.error("Failed to load knowledge base:", exc_info=e)
    
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
        # documents.extend(scrape_website(os.getenv("SITE_URL")))
        documents.extend(pdf_to_document(PDF_PATH))
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
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

    retriever = vector_store.as_retriever(search_kwargs={"k": 15})

except Exception as e:
    retriever = None
    logging.error("Vector store setup failed:", exc_info=e)

# --- Knowledge Retrieval ---

@tool
def knowledge_retriever_tool(query: str) -> str:
    """Search the restaurant knowledge base and return information."""
    if retriever is None:
        return "Service unavailable."
    docs = retriever.invoke(query)
    return "\n".join([doc.page_content for doc in docs]) if docs else "No relevant information found."

import time

@tool
def web_search_tool(query: str) -> str:
    """
    Perform a web search for the given query.
    """
    try:
        start_time = time.time()
        web_results = asyncio.run(custom_web_search(query))
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Time taken: {elapsed_time:.2f} seconds")
        return "\n".join(doc.page_content for doc in web_results) if web_results else "No relevant information found."
    except Exception as e:
        return f"Error performing web search: {str(e)}"