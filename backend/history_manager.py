import os, json

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "chat_history.json")

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def add_message(user_id, role, content):
    history = load_history()
    if user_id not in history:
        history[user_id] = []
    history[user_id].append({"role": role, "content": content})
    save_history(history)

def get_user_history(user_id):
    history = load_history()
    return history.get(user_id, [])
