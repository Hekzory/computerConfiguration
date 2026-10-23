#!/usr/bin/env python3
import os,pathlib,stat
h=pathlib.Path.home();p=h/'.config/confluence.token'
if p.stat().st_mode & 0o077:raise SystemExit('Confluence token file must be private (0600).')
token=p.read_text().strip()
if not token:raise SystemExit('Confluence token file is empty.')
exe=h/'.local/share/mcp-servers/node_modules/.bin/confluence-mcp-server'
env=dict(os.environ,CONFLUENCE_URL='https://confluence.vk.team',CONFLUENCE_EMAIL='-',CONFLUENCE_TOKEN=token)
os.execve(str(exe),[str(exe)],env)
