#!/usr/bin/env python3
import json, pathlib, re, subprocess, sys, urllib.parse
HOST = 'gitlab.corp.mail.ru'

def corporate(remote):
    if '://' in remote:
        return urllib.parse.urlsplit(remote).hostname == HOST
    m = re.match(r'(?:[^@/:]+@)?([^/:]+):', remote)
    return bool(m and m.group(1) == HOST)

def main():
    event=json.load(sys.stdin)
    cwd=event.get('cwd')
    if not cwd:return
    try:
        result=subprocess.run(['git','-C',cwd,'config','--get-all','remote.origin.url'],text=True,capture_output=True,timeout=3)
        if result.returncode or not any(corporate(x.strip()) for x in result.stdout.splitlines()):return
        text=(pathlib.Path.home()/'.local/share/agent-context/work.md').read_text()
    except (OSError, subprocess.TimeoutExpired, ValueError):return
    print(json.dumps({'hookSpecificOutput':{'hookEventName':'SessionStart','additionalContext':text}},ensure_ascii=False))

if __name__=='__main__':main()
