from pathlib import Path
import csv,json,datetime,re
DEST=Path('TOHOKU_CHECK/AUTHOR_PROOF_OBLIGATIONS.jsonl')
def add(fragment,status,title,claim,need,keywords,events=''):
 with open('TOHOKU_CHECK/proof-cues-interim-01/PARAGRAPH_FRAGMENTS.tsv',newline='') as f: lookup={r['fragment_id']:r for r in csv.DictReader(f,delimiter='\t')}
 r=lookup[fragment]
 old=[json.loads(s) for s in DEST.read_text().splitlines()] if DEST.exists() else []
 assert fragment not in {x['fragment_id'] for x in old}
 item={'fragment_id':fragment,'note_id':'OP-'+fragment,'printed_page':r['printed_page'],'source_file':r['file'],'source_lines':r['line']+'–'+r['end_line'],'source_fragment_sha256':r['paragraph_fragment_sha256'],'status':status,'title':title,'claim':claim,'proof_needs':need,'context_search_terms':keywords.split('|'),'related_check_event_ids':events.split('|') if events else [],'reviewer':'GPT-6 Astra; ChatGPT Pro mode; primary','reviewed_utc':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
 with DEST.open('a') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n')
