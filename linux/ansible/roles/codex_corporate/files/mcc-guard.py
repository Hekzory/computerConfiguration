#!/usr/bin/env python3
import json,pathlib,subprocess,sys,shlex

def main():
    event=json.load(sys.stdin)
    if event.get('tool_name') != 'Bash':return
    command=event.get('tool_input',{}).get('command')
    if not isinstance(command,str):return
    # Use the reviewed Claude guard as the common implementation; keep one check source.
    script=pathlib.Path.home()/'.codex/corporate/mcc-guard.sh'
    result=subprocess.run(['/usr/bin/bash',str(script)],input=json.dumps({'tool_input':{'command':command}}),text=True,capture_output=True,timeout=7)
    if result.returncode:raise RuntimeError('mcc guard failed')
    if result.stdout:
        output=json.loads(result.stdout)
        decision=output.get('hookSpecificOutput',{})
        if decision.get('hookEventName')!='PreToolUse' or decision.get('permissionDecision')!='deny':raise ValueError('Unexpected guard response')
        print(json.dumps(output,ensure_ascii=False))
        return
    # The old shell guard's logs pattern requires leading options. Also cover the
    # ordinary `mcc logs` spelling and absolute executable paths in Codex events.
    try:
        lexer=shlex.shlex(command,posix=True,punctuation_chars='|;&()')
        lexer.whitespace_split=True
        parts=list(lexer)
    except ValueError:return
    segment=[]
    for token in parts+[';']:
        if token in ['|','||','&','&&',';','(',')']:
            for i,word in enumerate(segment):
                if pathlib.PurePath(word).name!='mcc':continue
                args=segment[i+1:]
                if 'logs' in args and not any(x in args for x in ['--help','-h']) and not any(pathlib.PurePath(x).name=='timeout' for x in segment[:i]):
                    print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'mcc logs streams indefinitely; wrap it in a finite timeout (for example timeout 40 mcc -l -n NS logs INSTANCE STREAM).'}}))
                    return
            segment=[]
        else:segment.append(token)

if __name__=='__main__':main()
