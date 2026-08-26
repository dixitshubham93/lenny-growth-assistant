import requests

API = "http://localhost:8000/api/v1"
sid = requests.post(f"{API}/sessions").json()["session_id"]
print("Created:", sid)

# send msg
resp = requests.post(f"{API}/chat", json={"session_id": sid, "message": "hello"})
print("Chat resp:", resp.status_code)

# get history
hist = requests.get(f"{API}/sessions/{sid}/messages").json()
print("History length:", len(hist["messages"]))
if len(hist["messages"]) > 0:
    print("Has sources?", "sources" in hist["messages"][-1])
