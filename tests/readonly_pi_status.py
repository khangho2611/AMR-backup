"""Run via SSH stdin: process/port inventory only; never open a device."""
import datetime
import json
import pathlib
import subprocess

result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'boot':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
matches=[]
for item in pathlib.Path('/proc').iterdir():
    if not item.name.isdigit():continue
    try:
        args=(item/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace').strip()
        if any(v in args for v in ('agv_unified_brain.py','slam_toolbox','ldlidar','static_transform_publisher')):
            matches.append({'pid':int(item.name),'args':args,'cwd':str((item/'cwd').resolve())})
    except (OSError,ValueError):pass
result['processes']=matches
usb=subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True)
result.update(usb0_fuser_exit=usb.returncode,usb0_pids=usb.stdout.strip(),usb0_message=usb.stderr.strip())
ports=subprocess.run(['ss','-ltn'],capture_output=True,text=True)
result['http8080']=[s for s in ports.stdout.splitlines() if ':8080' in s]
print(json.dumps(result))
