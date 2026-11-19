"""Sequential scan-audit helpers. Run from the directory above TOHOKU_CHECK.

Inputs are the supplied archives extracted into input/scans and input/context.
These helpers record human/model decisions; they never certify an image reading.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import difflib
import json
import re
import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
PAGES = list(range(119, 184)) + list(range(185, 222))
LAYERS = {'dip': 'as-printed', 'fr': 'corrected', 'en': 'English'}
COLS = ['file', 'layer', 'printed_page', 'line', 'statement', 'old', 'new', 'evidence', 'kind', 'confidence']

def utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

def source(layer, page):
    return ROOT / 'sources' / layer / f'p{page}.tex'

def scan_id(page):
    return f"Part {'I' if page < 184 else 'II'}, PDF page {page - (118 if page < 184 else 184)}, printed p. {page}"

def render(page):
    done = [int(x) for x in re.findall(r'^page (\d+) done ', (ROOT/'progress.log').read_text(), re.M)]
    if page not in done:
        assert page == PAGES[len(done)], ('Out-of-order page', page, done[-1:] )
    part = 'I_printed_pp119-183' if page < 184 else 'II_printed_pp185-221'
    d = fitz.open(WORK/'input'/'scans'/f'TOHOKU_part_{part}.pdf')
    pix = d[page - (119 if page < 184 else 185)].get_pixmap(dpi=400)
    dest = WORK/'tmp'/'scans'; dest.mkdir(parents=True, exist_ok=True)
    pix.save(dest/f'p{page}.png')
    print(scan_id(page), '400 dpi:', pix.width, pix.height)

def crop(page, name, box, scale=2):
    im=Image.open(WORK/'tmp'/'scans'/f'p{page}.png').crop(box)
    im.resize((round(im.width*scale),round(im.height*scale))).save(WORK/'tmp'/'scans'/f'p{page}-{name}.png')

def show_text(page):
    for layer in ['dip', 'en']:
        print('\nLAYER', layer)
        for n,l in enumerate(source(layer,page).read_text().splitlines(),1):
            print(f'{n}: {l}')
    dip=source('dip',page).read_text().splitlines()
    fr=source('fr',page).read_text().splitlines()
    print('\nCORRECTED FRENCH DIFFERENCES (all other lines equal):')
    print('\n'.join(difflib.unified_diff(dip,fr,fromfile='dip',tofile='fr',lineterm='')))
    print('\nEXISTING SOURCE-CORRECTION RECORDS:')
    for l in (WORK/'input/context/edition_records/working_folder/SOURCE_CORRECTIONS.jsonl').read_text().splitlines():
        row=json.loads(l)
        if str(row.get('printed_page','')) == str(page):
            keep={k:v for k,v in row.items() if k in ['decision_id','record_id','diplomatic_reading','selected_corrected_french','classification','rationale','state','supersedes']}
            print(json.dumps(keep,ensure_ascii=False))

def change(layer, page, old, new, line, statement, evidence, kind='typesetting', count=1):
    p=source(layer,page) if layer in LAYERS else ROOT/'sources'/layer
    s=p.read_text()
    assert s.count(old)==count, (str(p.relative_to(ROOT)),old,s.count(old),count)
    s=s.replace(old,new)
    p.write_text(s)
    with (ROOT/'CORRECTIONS.tsv').open('a',newline='') as f:
        for occurrence in range(count):
            loc=line+(f'; occurrence {occurrence+1}/{count} in source order' if count>1 else '')
            row=[str(p.relative_to(ROOT)),LAYERS.get(layer,'build'),page,loc,statement,old,new,scan_id(page)+'; '+evidence,kind,'pending second reading']
            csv.writer(f,delimiter='\t').writerow(row)

def change_at(layer, page, start, old, new, line, statement, evidence, kind='typesetting'):
    """Change one visually classified occurrence at a verified character offset."""
    p = source(layer, page)
    s = p.read_text()
    assert s[start:start+len(old)] == old
    p.write_text(s[:start] + new + s[start+len(old):])
    with (ROOT/'CORRECTIONS.tsv').open('a', newline='') as f:
        csv.writer(f, delimiter='\t').writerow([
            str(p.relative_to(ROOT)), LAYERS[layer], page, line, statement,
            old, new, scan_id(page)+'; '+evidence, kind, 'pending second reading'])

def finish(page, details, verdicts, events=()):
    done = [int(x) for x in re.findall(r'^page (\d+) done ', (ROOT/'progress.log').read_text(), re.M)]
    assert page==PAGES[len(done)]
    t=utc()
    rows=list(csv.DictReader((ROOT/'CORRECTIONS.tsv').open(),delimiter='\t'))
    counts={l:sum(r['printed_page']==str(page) and r['layer']==l for r in rows) for l in LAYERS.values()}
    kinds={k:sum(r['printed_page']==str(page) and r['kind']==k for r in rows) for k in ['reading','misprint of the original','translation','typesetting','structure']}
    ranges='; '.join(f'`sources/{l}/p{page}.tex`, lines 1–{len(source(l,page).read_text().splitlines())}' for l in LAYERS)
    record=f'### Printed page {page}\n\n- Scan: {scan_id(page)}, rendered at 400 dpi and inspected, with enlarged crops at the decisions.\n- Reader: GPT-6 Astra (ChatGPT Pro mode), primary agent, sequential stream.\n- Sources compared: {ranges}. Diplomatic French against the image; corrected French against diplomatic French and the image; English paragraph by paragraph against corrected French.\n- Corrections in this pass: '+', '.join(f'{l}: {v}' for l,v in counts.items())+'. Kinds: '+', '.join(f'{k}: {v}' for k,v in kinds.items() if v)+'.\n- Existing corrected-layer decisions: '+verdicts+'\n- Reading observations: '+details+f'\n- Completed: {t}.\n\n'
    with (ROOT/'CHECK_RECORD.md').open('a') as f:f.write(record)
    for sid,typ,outcome in events:
        with (ROOT/'CHECK_EVENTS.tsv').open('a',newline='') as f:
            csv.writer(f,delimiter='\t').writerow([sid,t,'GPT-6 Astra; ChatGPT Pro; effort not exposed; TOHOKU second pass',typ,outcome])
    with (ROOT/'progress.log').open('a') as f:f.write(f'page {page} done {t}\n')
    print('Completed',page,t,counts)

def inherited(page, old, new, line, statement, evidence):
    """Record a retained difference already present between the French layers."""
    row=[f'sources/fr/p{page}.tex','corrected',page,line,statement,old,new,scan_id(page)+'; Inherited correction retained: '+evidence,'misprint of the original','pending second reading']
    with (ROOT/'CORRECTIONS.tsv').open('a',newline='') as f:
        csv.writer(f,delimiter='\t').writerow(row)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('page',type=int)
    args=parser.parse_args();render(args.page);show_text(args.page)
