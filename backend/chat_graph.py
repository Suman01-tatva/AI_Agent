import os
from typing import TypedDict
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END, START
from datetime import date
from typing import TypedDict, Annotated, Sequence
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from tools import all_tools
from knowledge_base import retriever_tool

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY missing in .env")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.5,
)

tools = all_tools + [retriever_tool]
llm = llm.bind_tools(tools)

# --- Agent State ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
current_date = date.today().isoformat()

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt.txt")

try:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    system_prompt = raw_prompt.format(current_date=current_date)
except FileNotFoundError:
    raise FileNotFoundError(f"Prompt file not found at {PROMPT_PATH}")

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="messages"),
    MessagesPlaceholder(variable_name="agent_scratchpad")
])

# --- Agent node ---
def call_agent(state: AgentState) -> AgentState:
    messages = state["messages"]
    formatted = prompt.format_prompt(messages=messages, agent_scratchpad=[]).to_messages()
    response = llm.invoke(formatted)
    tool_calls = getattr(response, "tool_calls", [])
    messages = state["messages"] + [AIMessage(content=getattr(response, "content", str(response)), tool_calls=tool_calls)]
    return {"messages": messages}


tools_dict = {tool.name: tool for tool in tools}

def call_tool(state: AgentState) -> AgentState:
    tool_calls = getattr(state["messages"][-1], 'tool_calls', [])
    messages = state["messages"]
    
    for t in tool_calls:
        print(f"Calling Tool: {t['name']} with args: {t['args']}")
        if t['name'] not in tools_dict:
            result = f"<div><p>Incorrect Tool Name, Please Retry and Select tool from List of Available tools.</p></div>"
        else:
            result = tools_dict[t['name']].invoke(t['args'])
        messages.append(ToolMessage(content=str(result), tool_call_id=t["id"], name=t["name"]))
    
    return {"messages": messages}

def should_continue(state: AgentState) -> bool:
    return len(getattr(state["messages"][-1], "tool_calls", [])) > 0

def build_chat_graph():
    workflow = StateGraph(AgentState)
    # Add nodes
    workflow.add_node("agent", call_agent)
    workflow.add_node("tool", call_tool)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, {True: "tool", False: END})
    workflow.add_edge("tool", "agent")
    agent = workflow.compile(checkpointer=MemorySaver())
    return agent
