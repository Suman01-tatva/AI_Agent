import os
from typing import TypedDict
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langgraph.graph import StateGraph
from datetime import date
from tools import all_tools

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY missing in .env")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.5,
    google_api_key=api_key,
)

# Initialize memory
memory = ConversationBufferMemory(return_messages=True, memory_key="chat_history")

tools = all_tools

current_date = date.today().isoformat()

with open("prompt.txt", "r", encoding="utf-8") as f:
    raw_prompt = f.read()

    system_prompt = raw_prompt.format(current_date=current_date)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)

class ChatState(TypedDict):
    messages: list
    tool_calls: list

def call_agent(state: ChatState, config: RunnableConfig):
    messages = state["messages"]
    chat_history = memory.load_memory_variables({})["chat_history"]
    input_message = state["messages"][-1].content
    
    result = agent_executor.invoke(
        {
            "input": input_message,
            "chat_history": chat_history,
            "current_date": current_date,
        }
    )

    # Save the conversation to memory
    memory.save_context(
        {"input": input_message},
        {"output": result["output"] if isinstance(result, dict) and "output" in result else str(result)}
    )
    
    if isinstance(result, dict) and "tool_calls" in result:
        return {"messages": messages, "tool_calls": result["tool_calls"]}

    return {"messages": messages + [result], "tool_calls": []}

def call_tool(state: ChatState, config: RunnableConfig):
    
    messages = state["messages"]
    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        return {"messages": messages, "tool_calls": []}

    results = []

    for call in tool_calls:
        tool_name = call["tool"]
        tool_args = call["tool_input"]

        tool_fn = next((t for t in tools if t.name == tool_name), None)
        if not tool_fn:
            memory.save_context({}, {"output": results.content})
            results.append(AIMessage(content=f"❌ Tool '{tool_name}' not found."))
            continue

        try:
            output = tool_fn.invoke(tool_args)
            memory.save_context({}, {"output": output})
            results.append(AIMessage(content=output))
        except Exception as e:
            memory.save_context({}, {"output": e})
            print(f"❌ Error in tool '{tool_name}': {e}")
            results.append(AIMessage(content=f"❌ Failed to run {tool_name}: {str(e)}"))

    return {"messages": messages + results, "tool_calls": []}

def build_chat_graph():
    workflow = StateGraph(ChatState)

    # Pass-through start and end nodes
    def start_node(state: ChatState, config: RunnableConfig):
        return state

    def end_node(state: ChatState, config: RunnableConfig):
        return state

    # Add nodes
    workflow.add_node("start", start_node)
    workflow.add_node("agent", call_agent)
    workflow.add_node("tool", call_tool)
    workflow.add_node("end", end_node)

    # Entry and exit points
    workflow.set_entry_point("start")

    # Define graph structure
    workflow.add_edge("start", "agent")

    def route(state: ChatState):
        if state.get("tool_calls"):
            return "tool"
        return "end"

    workflow.add_conditional_edges("agent", route)
    workflow.add_edge("tool", "agent")

    # Explicitly finish at "end"
    workflow.set_finish_point("end")

    return workflow.compile()
