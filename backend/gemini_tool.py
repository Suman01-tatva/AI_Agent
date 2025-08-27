# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain.agents import initialize_agent, Tool
# from langchain.memory import ConversationBufferMemory
import requests
from langchain_core.tools import tool
# from dotenv import load_dotenv
# import os

# ---------- Load env ----------
# load_dotenv()
# GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# if not GOOGLE_API_KEY:
#     raise ValueError("GOOGLE_API_KEY missing in .env")

# ------------------ Gemini Tool ------------------
@tool
def gemini_tool(prompt: str) -> str:
    """Use Gemini API for everything: Q&A, calculations, reasoning."""
    print("Calling Gemini API...")
    MODEL = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GOOGLE_API_KEY}"
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=data,
    )
    if response.ok:
        return response.json()
    return f"Error: {response.status_code}"

# # Wrap Gemini as a single LangChain tool
# tools = [Tool(name="Gemini", func=gemini_tool, description="Answer questions, solve math, reason, search info")]

# # ------------------ Memory ------------------
# memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# # ------------------ Agent ------------------
# agent = initialize_agent(
#     tools,
#     ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7, api_key="AIzaSyAK1P3R0fnbic1o6OU4xT8FuhfXD3XZQmE"),
#     agent="chat-conversational-react-description",
#     memory=memory,
#     verbose=True
# )

# # ------------------ Chat Loop ------------------
# print("Autonomous Gemini Chatbot (type 'exit' to quit)")

# while True:
#     user_input = input("You: ")
#     if user_input.lower() == "exit":
#         break
    
#     # Agent plans, reasons, and answers using Gemini only
#     response = agent.invoke(user_input)
#     print("Agent:", response["output"])

