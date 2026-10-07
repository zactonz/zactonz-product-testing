import urllib.request, threading, json, sys
B="http://127.0.0.1:8910"; TOK="Bearer tok-alice"; N=int(sys.argv[1]) if len(sys.argv)>1 else 15
def reset():
    req=urllib.request.Request(B+"/me",data=b'{"jobs_used":0}',method="PATCH",
        headers={"Authorization":TOK,"Content-Type":"application/json"})
    urllib.request.urlopen(req).read()
def fire(out,i):
    req=urllib.request.Request(B+"/jobs",data=b"",method="POST",headers={"Authorization":TOK})
    try:
        r=urllib.request.urlopen(req); out[i]=(r.status,r.read().decode())
    except urllib.error.HTTPError as e:
        out[i]=(e.code,e.read().decode())
reset()
out=[None]*N; ts=[threading.Thread(target=fire,args=(out,i)) for i in range(N)]
for t in ts: t.start()
for t in ts: t.join()
codes=[c for c,_ in out]
ok=codes.count(201); over=codes.count(429); err=sum(1 for c in codes if c>=500)
print(f"fired {N} concurrent POST /jobs against QUOTA=3")
print(f"  201 (queued)      : {ok}")
print(f"  429 (quota)       : {over}")
print(f"  500 (error)       : {err}")
useds=sorted({json.loads(b).get('used') for c,b in out if c==201})
print(f"  distinct 'used' values returned among 201s: {useds}")
print(f"  VERDICT: {'RACE — more than 3 queued' if ok>3 else 'quota held'}")
