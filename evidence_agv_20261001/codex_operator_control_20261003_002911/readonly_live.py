import datetime,json,pathlib,subprocess,urllib.request
root=pathlib.Path('/home/khangho/agv_codex_operator_20261003_002911')
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
     'boot':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
for endpoint in ('telemetry','diagnostics'):
    try:
        out[endpoint]=json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/'+endpoint,timeout=3))
    except Exception as exc:out[endpoint]={'error':str(exc)}
out['logs']={name:(root/'runtime'/f'{name}.log').read_text(errors='replace')[-6000:]
             for name in ('brain','lidar','slam') if (root/'runtime'/f'{name}.log').exists()}
out['owner']=subprocess.run(['fuser','/dev/ttyUSB0','/dev/ttyUSB1'],capture_output=True,text=True).stdout
print(json.dumps(out))
