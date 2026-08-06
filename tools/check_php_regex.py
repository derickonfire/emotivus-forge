#!/usr/bin/env python3
"""
PHP regex delimiter check.

WHY THIS EXISTS
---------------
v2.575 shipped a staging defect where a preg_replace() pattern used '#' as its
delimiter while the pattern body contained the HTML entity &#039;. PHP ended the
pattern at that '#', the regex was malformed, preg_replace() returned NULL, and
EVERY rich() field on the site rendered empty — all H1s, eyebrows and body copy
vanished.

Neither `php -l` nor a structural check catches this: the FILE is syntactically
valid. The failure is inside a string literal, at runtime.

WHAT IT CHECKS
--------------
For every preg_* call with a single-quoted pattern, whether the closing
delimiter also appears UNESCAPED inside the pattern body.

Usage:  python3 tools/check_php_regex.py <root>
Exit 0 = clean, 1 = at least one collision.
"""
import re, sys, os

def php_unquote(lit):
    out=[];k=0
    while k<len(lit):
        if lit[k]=='\\' and k+1<len(lit) and lit[k+1] in ("'","\\"):
            out.append(lit[k+1]);k+=2
        else:
            out.append(lit[k]);k+=1
    return ''.join(out)

CALL=re.compile(r"preg_(?:match|match_all|replace|replace_callback|split)\s*\(\s*'((?:[^'\\]|\\.)*)'")
PAIRS={'(':')','{':'}','[':']','<':'>'}

def check(path):
    try:
        src=open(path,encoding='utf-8',errors='replace').read()
    except OSError:
        return []
    bad=[]
    for m in CALL.finditer(src):
        p=php_unquote(m.group(1))
        if len(p)<2: continue
        d=p[0]
        if d.isalnum() or d.isspace(): continue
        close=PAIRS.get(d,d)
        end=p.rfind(close)
        if end<=0: continue
        body=p[1:end]
        hits=[i for i in range(len(body)) if body[i]==close and (i==0 or body[i-1]!='\\')]
        if hits:
            line=src[:m.start()].count('\n')+1
            bad.append(f"{path}:{line}: delimiter {d!r} also appears unescaped in the "
                       f"pattern body — PHP will end the pattern early and preg_* "
                       f"will return NULL. Use a delimiter that cannot occur in the "
                       f"body (e.g. ~ or #). Pattern: {p[:70]}")
    return bad

def main(argv):
    root=argv[1] if len(argv)>1 else '.'
    problems=[];count=0
    for dirpath,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d not in ('.git','node_modules','phpmailer','vendor')]
        for f in sorted(files):
            if f.endswith('.php'):
                count+=1
                problems+=check(os.path.join(dirpath,f))
    if problems:
        print(f"REGEX DELIMITER COLLISIONS ({len(problems)}):\n")
        for p in problems: print("  "+p)
        print(f"\nScanned {count} file(s).")
        return 1
    print(f"OK — {count} PHP file(s); no regex delimiter collisions.")
    return 0

if __name__=='__main__':
    sys.exit(main(sys.argv))
