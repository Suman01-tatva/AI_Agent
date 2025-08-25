import asyncio
import json
from dotenv import load_dotenv
from typing import List
from langchain_core.documents import Document
from ddgs import DDGS
from langchain.text_splitter import RecursiveCharacterTextSplitter
# from crawl4ai import AsyncWebCrawler
# import trafilatura
from tenacity import retry, stop_after_attempt, wait_fixed
from sentence_transformers import SentenceTransformer, util
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

load_dotenv()

# ✅ Playwright scraper
async def scrape_with_playwright(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        content = await page.content()
        await browser.close()
        return content
    
# Initialize embedding model
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def search_web(query: str, max_results: int = 5) -> List[Document]:
    # Step 1: DuckDuckGo Search
    def do_search():
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    results = await asyncio.to_thread(do_search)
    urls = [r.get('href') or r.get('url') for r in results if r.get('href') or r.get('url')]
    print("🔎 Found URLs:", urls)

    # Step 2: Scrape & Clean
    async def extract_from_url(url):
        try:
            html = await scrape_with_playwright(url)
            soup = BeautifulSoup(html, "html.parser")
            for s in soup(["script", "style", "noscript"]):
                s.extract()
            text = soup.get_text(separator=" ", strip=True)
            if not text:
                return []
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=150
            )
            doc = Document(page_content=text, metadata={"source": url})
            chunks = text_splitter.split_documents([doc])
            for chunk in chunks:
                chunk.metadata["url"] = url
            return chunks

        except Exception as e:
            return [Document(page_content=f"Failed to scrape: {str(e)}", metadata={"url": url})]
    tasks = [extract_from_url(url) for url in urls[:max_results]]
    results = await asyncio.gather(*tasks)
    all_chunks = [doc for sublist in results for doc in sublist]
    return [doc for doc in all_chunks if "Failed to scrape" not in doc.page_content]

# Rank snippets by semantic similarity
def rank_snippets(query: str, documents: List[Document]) -> List[Document]:
    query_emb = embed_model.encode(query, convert_to_tensor=True)
    ranked_docs = []
    for doc in documents:
        content = doc.page_content
        if "Failed to scrape" in content:
            continue
        doc_emb = embed_model.encode(content, convert_to_tensor=True)
        score = float(util.pytorch_cos_sim(query_emb, doc_emb))
        if score < 0.5:  # threshold to filter out low relevance
            continue
        # put score in metadata
        new_metadata = {**doc.metadata, "score": score}
        ranked_docs.append(Document(page_content=doc.page_content, metadata=new_metadata))
    return sorted(ranked_docs, key=lambda d: d.metadata.get("score", 0), reverse=True)

# Full pipeline
async def custom_web_search(query: str, max_results: int = 5) -> List[Document]:
    web_docs = await search_web(query, max_results)
    ranked_docs = rank_snippets(query, web_docs)
    return ranked_docs
    