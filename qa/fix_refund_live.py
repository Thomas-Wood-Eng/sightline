"""Live sandbox: buy, return, then drop the connection right after sending the PIN (the page closed),
reopen, and check the session is clean. Usage: python qa/fix_refund_live.py [port]"""
import sys, time
import httpx
BASE = f"http://127.0.0.1:{sys.argv[1] if len(sys.argv) > 1 else 8791}"
c = httpx.Client(base_url=BASE, timeout=60)
turn = lambda text: c.post('/api/turn', json={'text': text}).json()
c.get('/api/settings')
assert c.post('/api/onboarding', json={'screen_reader': True, 'pin': '1234'}).status_code == 200
turn('find me a warm hoodie'); turn('add the first one in medium'); print(turn('check out')['lines'][-6:-4])
turn('confirm'); print(c.post('/api/pin', json={'pin': '1234'}).json()['say'])
time.sleep(10.5); print(c.post('/api/finalize').json()['say'])
r = turn('return the hoodie'); print(r['say'], r['lines'][1]); turn('confirm')
try:  # close the page right after the PIN: the reply never arrives
    c.post('/api/pin', json={'pin': '1234'}, timeout=0.3)
except httpx.TimeoutException:
    print('connection dropped before the reply')
time.sleep(6)  # PayPal finishes the refund server-side
s = c.get('/api/settings').json(); print('state after reopening:', s['state'])
print('my orders:', turn('my orders')['lines'][0])
print('cancel:', turn('cancel')['say'])
print('anything:', turn('what is in my cart')['say'])
