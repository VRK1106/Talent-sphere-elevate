import urllib.request
import urllib.parse
import json
import http.cookiejar

# Create a cookie jar to maintain session/cookies
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Use a specific tab ID
tab_id = "test-tab-123"

# 1. Login (with tab_id query param to ensure session is associated)
login_url = f"http://127.0.0.1:5000/login?tab_id={tab_id}"
login_data = urllib.parse.urlencode({
    'username': 'emp01',
    'password': 'jane1234',
    'tab_id': tab_id
}).encode('utf-8')

req = urllib.request.Request(login_url, data=login_data, method='POST')
with opener.open(req) as resp:
    print("Login Response Status:", resp.status)
    # Read response to complete it
    html = resp.read().decode('utf-8')
    print("Login Response Length:", len(html))

# 2. Get the assistant page
assistant_url = f"http://127.0.0.1:5000/assistant?tab_id={tab_id}"
with opener.open(assistant_url) as resp:
    print("Assistant Page Status:", resp.status)
    html = resp.read().decode('utf-8')
    print("Assistant Page contains chat input:", "chatInput" in html or "message" in html)

# 3. Create a chat session
create_session_url = f"http://127.0.0.1:5000/assistant/session/create?tab_id={tab_id}"
with opener.open(create_session_url) as resp:
    print("Create Session Status:", resp.status)
    resp.read()

# 4. Post chat stream query
chat_url = f"http://127.0.0.1:5000/assistant/chat_stream?tab_id={tab_id}"
chat_data = json.dumps({
    'query': 'Heat treatment of steel',
    'model': 'meta-llama/llama-4-scout-17b-16e-instruct',
    'mode': 'RAG (Document Guided)',
    'tab_id': tab_id
}).encode('utf-8')

req = urllib.request.Request(chat_url, data=chat_data, headers={'Content-Type': 'application/json'}, method='POST')
try:
    with opener.open(req) as resp:
        print("Chat Stream Status:", resp.status)
        # Read stream
        while True:
            chunk = resp.read(1)
            if not chunk:
                break
            # print without emoji encoding issues on windows console
            char = chunk.decode('utf-8', errors='ignore')
            try:
                print(char, end='', flush=True)
            except UnicodeEncodeError:
                pass
except Exception as e:
    print("\nError calling chat stream:", e)
