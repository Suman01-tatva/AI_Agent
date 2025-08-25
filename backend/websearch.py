import asyncio
from asyncio import wait_for
from dotenv import load_dotenv
from typing import List
from langchain_core.documents import Document
from langchain_community.document_loaders import UnstructuredURLLoader
from ddgs import DDGS
from langchain.text_splitter import RecursiveCharacterTextSplitter
# from crawl4ai import AsyncWebCrawler
# import trafilatura
from tenacity import retry, stop_after_attempt, wait_fixed
from sentence_transformers import SentenceTransformer, util

load_dotenv()
# Initialize embedding model
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# Caching (in-memory fallback, can replace with Redis later)
# use_redis = False
# redis_client = {}

# Cache helper functions
# def get_cached_result(query: str) -> Optional[List[Document]]:
#     if use_redis:
#         cached = redis_client.get(query)
#         if cached:
#             docs_data = json.loads(cached)
#             return [Document(page_content=d["page_content"], metadata=d["metadata"]) for d in docs_data]
#     return None
        
# def cache_result(query: str, results: List[Document]) -> None:
#     serialized = [{"page_content": d.page_content, "metadata": d.metadata} for d in results]
#     if use_redis:
#         redis_client.setex(query, 86400, json.dumps(serialized))  # store JSON
#     else:
#         redis_client[query] = results

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def search_web(query: str, max_results: int = 5) -> List[Document]:
    # cached = get_cached_result(query)
    # if cached:
    #     print("🔍 Using cached results for:", query)
    #     return cached

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
            loader = UnstructuredURLLoader(urls=[url])
            docs = await asyncio.to_thread(loader.load)
            if not docs:
                return []

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=150
            )
            chunks = text_splitter.split_documents(docs)
            for chunk in chunks:
                chunk.metadata["url"] = url
            return chunks

        except Exception as e:
            return [Document(page_content=f"Failed to scrape: {str(e)}", metadata={"url": url})]
        
    tasks = [wait_for(extract_from_url(url), timeout=15) for url in urls[:max_results]]
    # tasks = [extract_from_url(url) for url in urls[:max_results]]
    
    results = await asyncio.gather(*tasks,return_exceptions=True)
    all_chunks = []
    for sublist in results:
        if isinstance(sublist, Exception):
            continue
        all_chunks.extend(sublist)
    return [doc for doc in all_chunks if "Failed to scrape" not in doc.page_content]

# Rank snippets by semantic similarity
def rank_snippets(query: str, documents: List[Document]) -> List[Document]:
    query_emb = embed_model.encode(query, convert_to_tensor=True)
    contents = [doc.page_content for doc in documents if "Failed to scrape" not in doc.page_content]
    if not contents:
        return []

    doc_embs = embed_model.encode(contents, convert_to_tensor=True)
    ranked_docs = []
    for doc, doc_emb in zip(documents, doc_embs):
        score = float(util.pytorch_cos_sim(query_emb, doc_emb))
        if score < 0.6:
            continue
        new_metadata = {**doc.metadata, "score": score}
        ranked_docs.append(Document(page_content=doc.page_content, metadata=new_metadata))

    return sorted(ranked_docs, key=lambda d: d.metadata.get("score", 0), reverse=True)

# Full pipeline
async def custom_web_search(query: str, max_results: int = 5) -> List[Document]:
    web_docs = await search_web(query, max_results)
    ranked_docs = rank_snippets(query, web_docs)
    return ranked_docs
