import requests

API = "http://localhost:8000/api/v1"

# 1. Create session (like New Chat click)
res = requests.post(f"{API}/sessions")
sid = res.json()["session_id"]
print(f"Created Session 1: {sid}")

# 2. Send message
requests.post(f"{API}/chat", json={"session_id": sid, "message": "hello world"})

# 3. Fetch history (simulating page refresh loading from backend)
history_res = requests.get(f"{API}/sessions/{sid}/messages").json()
hist = history_res["messages"]

print(f"Messages after refresh: {len(hist)}")
print(f"Message 1 role: {hist[0]['role']}, content: {hist[0]['content']}")
print(f"Message 2 role: {hist[1]['role']}, content: {hist[1]['content']}")
print(f"Message 2 sources: {hist[1].get('sources')}")

# 4. Create NEW session (like New Chat click)
sid2 = requests.post(f"{API}/sessions").json()["session_id"]
print(f"\nCreated Session 2: {sid2}")

hist2 = requests.get(f"{API}/sessions/{sid2}/messages").json()["messages"]
print(f"Session 2 initial messages: {len(hist2)}")
