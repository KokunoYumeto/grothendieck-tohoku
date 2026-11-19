import csv,json
from pathlib import Path
root=Path('TOHOKU_CHECK')
maps=list(csv.DictReader(Path('input/context/stacks/tohoku_r71/map.csv').open()))
units={x['id']:x for x in csv.DictReader(Path('input/context/stacks/tohoku_r71/units.csv').open())}
byid={x['unit_id']:(i+1,x) for i,x in enumerate(maps)}
event_source=root/'CHECK_EVENTS.before-note-bindings.tsv'
if not event_source.exists():event_source=root/'CHECK_EVENTS.tsv'
events=list(csv.DictReader(event_source.open(),delimiter='\t'))
# Every selection below was assigned by the primary after reading the source and the
# current contextual index. A shared surrounding unit is labelled as surrounding
# context in the final note; it is never treated as an exact theorem equivalence.
chosen={
0:901,1:737,2:628,3:974,4:976,5:739,6:983,7:983,8:579,9:260,10:906,11:906,12:744,13:751,14:909,15:653,16:754,17:314,18:629,19:758,20:285,21:584,22:760,23:167,24:88,25:87,26:120,27:259,28:283,29:960,30:321,31:171,32:171,33:661,34:151,35:666,36:961,37:667,38:293,39:293,40:299,41:669,42:450,43:642,44:963,45:963,46:633,47:633,48:917,49:917,50:425,51:425,52:425,53:576,54:576,55:77,56:227,57:228,58:964,59:772,60:772,61:772,62:45,63:848,64:767,65:220,66:220,67:768,68:768,
69:343,70:350,71:'tohoku:proposition:4.1.1',72:634,73:'tohoku:proposition:4.1.2',74:'tohoku:proposition:4.1.3',75:161,76:965,77:401,78:966,79:'tohoku:proposition:4.2.3',80:777,81:'tohoku:eq:4.2.10-bis',82:393,83:'tohoku:corollary:4.2.4:3',84:'tohoku:lemma:4.3:gamma-injective',85:'tohoku:theorem:4.3.1',86:'tohoku:proposition:4.3.2',87:234,88:235,89:809,90:255,91:588,92:922,93:968,94:721,95:721,96:940,97:173,98:779,99:780,100:182,101:677,102:692,103:490,104:590,105:590,106:491,107:853,108:693,109:'tohoku:theorem:5.2.1',110:924,111:783,112:'tohoku:proposition:5.2.3',113:'tohoku:corollary:5.2.3',114:785,115:'tohoku:equation:5.2.12',116:495,117:819,118:970,119:'tohoku:corollary:5.3.1:1',120:819,121:695,122:'tohoku:corollary:5.3.1:3',123:942,124:786,125:242,126:242,127:845,128:636,129:636,130:'tohoku:lemma:5.5.2',131:'tohoku:lemma:5.5.2',132:971,133:338,134:682,135:78,136:78,137:245,138:509,139:795,140:796,141:699,142:166,143:166,144:514,145:638,146:705,147:705,148:95,149:607,150:532,151:537,152:766,153:538,154:'tohoku:construction:product-hom-sheaf',155:'tohoku:construction:product-hom-sheaf',156:'tohoku:construction:product-hom-sheaf',157:244,158:244,159:639,160:135,161:209,162:548,163:790,164:973,165:945,166:591,167:117,168:'tohoku:equation:5.6.12',169:951,170:946,171:953,172:589,173:561,174:589,175:186,176:542,177:543,178:'tohoku:construction:extension-by-zero-support-limit',179:544,180:97,181:61,
182:425,183:576,184:964,185:964,186:772,187:901,188:737,189:739,190:983,191:983,192:579,193:260,194:285,195:343,196:161,197:721,198:242,199:845,200:'tohoku:construction:product-hom-sheaf',201:245,202:796,203:739,204:983,205:'tohoku:lemma:5.5.2',206:97,207:799,208:799,209:569}
assert len(chosen)==210
out={};extra={};missing=[]
read={json.loads(s)['map_record'] for s in (root/'notes-context-primary-review-interim-01/MAP_RECORDS_READ.jsonl').read_text().splitlines()}
for i,x in chosen.items():
    if isinstance(x,int):rec,m=x,maps[x-1]
    elif x in byid:rec,m=byid[x]
    else:
        missing.append((i,x,[k for k in byid if x.rsplit(':',1)[-1] in k]));continue
    sid=events[i]['statement_id']
    out[sid]={'note_id':sid,'context_unit_id':m['unit_id'],'map_logical_record':rec,'map_physical_line':rec+1,'selection':'explicit primary selection of the same statement or its named surrounding context; exact scope stated in note','rationale':m['rationale'],'disposition':m['disposition'],'title':units[m['unit_id']]['title_en'],'source_item':m['item']}
    if rec not in read:extra[rec]={'map_record':rec,**m,'title_en':units[m['unit_id']]['title_en']}
if missing:
 print('MISSING',json.dumps(missing,ensure_ascii=False,indent=2));raise SystemExit(1)
(root/'MATHEMATICAL_NOTE_CONTEXT_SELECTION.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in out.values()))
Path('tmp/context-primary/extra-selected-map.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in extra.values()))
print('203 note selections',len(out),'additional records to read',len(extra))
print(Path('tmp/context-primary/extra-selected-map.jsonl').read_text())
