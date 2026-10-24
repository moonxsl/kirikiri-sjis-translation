# -*- coding: utf-8 -*-
"""Extract KAG dialogue from unpacked *.ks into GalTransl's gt_input JSON.

This is the step the guide used to leave as prose. It is deliberately
conservative: it only recognises the two shapes that older KAG dialects share
(an optional `【name】` line, then one text line), and it strips every `[tag]`
from the message so the rewrite side can match the visible text.

Run `krr.py unpack` first (or pass --ks-dir at the extracted scenario folder),
then:

    python extract.py --game "D:\\Game" [--text "D:\\Game\\文本"] [--dry-run]

Output: <text>/gt_input/<script>.json  ->  [{"name": ..., "message": ...}, ...]
Names are kept in the separate `name` field, which is what GalTransl expects;
`krr.py rewrite` also accepts the merged `【name】\\n` form on the translated side.
"""
import argparse
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):          # keep CJK output from dying on a GBK console
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

TAG = re.compile(r'\[[^\[\]]*\]')
NAME_ONLY = re.compile(r'^【([^】]*)】$')
COMMENT = re.compile(r'^\s*;')


def strip_tags(line):
    """Drop every [...] cluster, tolerating nesting and quoted brackets."""
    out, depth = [], 0
    for ch in line:
        if ch == '[':
            depth += 1
        elif ch == ']':
            if depth:
                depth -= 1
        elif depth == 0:
            out.append(ch)
    return ''.join(out)


def visible(line):
    return strip_tags(line).strip()


def parse_script(text):
    """Yield dicts in file order: {"name": ...} and/or {"message": ...}."""
    out, pending, in_script = [], None, False
    for raw in text.split('\n'):
        line = raw.rstrip('\r')
        low = line.lower()
        if '[iscript]' in low:            # TJS block: not dialogue
            in_script = True
            continue
        if '[endscript]' in low:
            in_script = False
            continue
        if in_script:
            continue
        if not line.strip() or COMMENT.match(line):
            continue
        stripped = line.lstrip()
        if stripped.startswith('*'):          # label
            continue
        if stripped.startswith('@'):          # KAG command
            continue
        vis = visible(line)
        if not vis:
            continue
        if '[' in vis or ']' in vis:          # unbalanced brackets = command leftovers
            continue
        m = NAME_ONLY.match(vis)
        if m:
            pending = m.group(1).strip()
            continue
        entry = {'message': vis}
        if pending:
            entry['name'] = pending
            pending = None
        out.append(entry)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--game', required=True)
    p.add_argument('--text', help='translation root (default: <game>/文本)')
    p.add_argument('--work', help='working dir holding extracted/ (default: <game>/_work)')
    p.add_argument('--ks-dir', help='override: folder with the unpacked .ks files')
    p.add_argument('--ext', default='.ks')
    p.add_argument('--skip', default='', help='comma separated stems to skip')
    p.add_argument('--dry-run', action='store_true', help='print, write nothing')
    p.add_argument('--compare', help='reference gt_input folder: report per-script count diffs')
    c = p.parse_args(argv)

    text_root = c.text or os.path.join(c.game, '文本')
    work = c.work or os.path.join(c.game, '_work')
    ks_dir = c.ks_dir or os.path.join(work, 'extracted', 'scenario')
    out_dir = os.path.join(text_root, 'gt_input')
    skip = {s.strip() for s in c.skip.split(',') if s.strip()}

    if not os.path.isdir(ks_dir):
        sys.exit('no script folder at %s (run `krr.py unpack` first)' % ks_dir)

    files = sorted(f for f in os.listdir(ks_dir) if f.lower().endswith(c.ext))
    if not files:
        sys.exit('no *%s under %s' % (c.ext, ks_dir))

    total_msgs = total_chars = 0
    diffs = []
    for name in files:
        base = os.path.splitext(name)[0]
        if base in skip:
            continue
        path = os.path.join(ks_dir, name)
        raw = open(path, 'rb').read()
        try:
            text = raw.decode('cp932')
        except UnicodeDecodeError as ex:
            print('  skip %-24s (not CP932: %s)' % (name, ex))
            continue
        entries = parse_script(text)
        msgs = [e for e in entries if 'message' in e]
        chars = sum(len(e['message']) for e in msgs)
        total_msgs += len(msgs)
        total_chars += chars
        if c.compare:
            ref = os.path.join(c.compare, base + '.json')
            if os.path.exists(ref):
                want = len([e for e in json.load(open(ref, encoding='utf-8'))
                            if 'message' in e])
                ok = want == len(msgs)
                if not ok:
                    diffs.append((base, len(msgs), want))
                print('%-20s %4d vs %4d  %s' % (name, len(msgs), want, 'OK' if ok else 'DIFF'))
        if c.dry_run:
            print('%s: %d messages, %d chars' % (name, len(msgs), chars))
            for e in entries[:4]:
                print('   ', json.dumps(e, ensure_ascii=False)[:90])
            continue
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, base + '.json'), 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    if c.dry_run:
        print('\nTOTAL %d messages, %d chars (dry run, nothing written)' % (total_msgs, total_chars))
    else:
        print('wrote %s -> %d messages, %d chars' % (out_dir, total_msgs, total_chars))
    if c.compare:
        print('\ncount diffs vs %s: %d script(s)' % (c.compare, len(diffs)))
        for b, got, want in diffs:
            print('   %-20s extracted %d, reference %d' % (b, got, want))


if __name__ == '__main__':
    main()
