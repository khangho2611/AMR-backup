import json
import urllib.request

d = json.loads(urllib.request.urlopen('http://127.0.0.1:8080/api/diagnostics').read())
events = d.get('events', [])
non_d0 = [e for e in events if e.get('kind') != 'rx_d0']
print(f'Total non-d0 events: {len(non_d0)}')
for e in non_d0[-40:]:
    print(e.get('mono'), e.get('kind'), {k:v for k,v in e.items() if k not in ('kind','mono','sequence')})
