import os
from typing import TypedDict, Annotated, Sequence
from dotenv import load_dotenv
from datetime import date
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
# Local imports
from tools import all_tools
from knowledge_base import retriever_tool


# --- ENV SETUP ---
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY missing in .env")

# --- LLM SETUP ---
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.5,
)

tools = all_tools + [retriever_tool]
llm = llm.bind_tools(tools)


# --- Agent State ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# --- System Prompt ---
current_date = date.today().isoformat()
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt.txt")

try:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    system_prompt = raw_prompt.format(current_date=current_date)
except FileNotFoundError:
    system_prompt = (
        f"You are a helpful **restaurant reservation assistant**. "
        f"Today's date is {current_date}. "
        f"Your tasks:\n"
        f"- Help users book, retrieve, update, and cancel reservations.\n"
        f"- Always validate inputs (date > today, time within restaurant hours).\n"
        f"- Use search tool for food/restaurant/general knowledge queries.\n"
        f"- Be polite, concise, and professional."
    )

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="messages"),
])


# --- Agent Node ---
def call_agent(state: AgentState) -> AgentState:
    """Call the LLM with the conversation state."""
    messages = state["messages"]
    formatted = prompt.format_prompt(messages=messages).to_messages()
    response = llm.invoke(formatted)

    tool_calls = getattr(response, "tool_calls", [])
    messages = messages + [
        AIMessage(
            content=getattr(response, "content", str(response)),
            tool_calls=tool_calls
        )
    ]
    return {"messages": messages}


# --- Tool Node ---
tools_dict = {tool.name: tool for tool in tools}


def call_tool(state: AgentState) -> AgentState:
    """Execute tool calls from the LLM response."""
    tool_calls = getattr(state["messages"][-1], "tool_calls", [])
    messages = state["messages"]

    print(f"🔧 Available tools: {list(tools_dict.keys())}")

    for t in tool_calls:
        tool_name = t["name"]
        tool_args = t["args"]
        print(f"⚡ Calling Tool: {tool_name} with args: {tool_args}")

        if tool_name not in tools_dict:
            result = f"❌ Error: Tool `{tool_name}` not found."
        else:
            try:
                raw_result = tools_dict[tool_name].invoke(tool_args)
                # Serialize safely
                result = str(raw_result) if raw_result is not None else "No result."
            except Exception as e:
                result = f"❌ Tool `{tool_name}` failed: {str(e)}"

        messages.append(
            ToolMessage(content=result, tool_call_id=t["id"], name=tool_name)
        )

    return {"messages": messages}


# --- Router ---
def should_continue(state: AgentState) -> bool:
    """Check if agent requested tool calls."""
    return len(getattr(state["messages"][-1], "tool_calls", [])) > 0


# --- Workflow Build ---
def build_chat_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", call_agent)
    workflow.add_node("tool", call_tool)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {True: "tool", False: END}
    )
    workflow.add_edge("tool", "agent")

    return workflow.compile(checkpointer=MemorySaver())
