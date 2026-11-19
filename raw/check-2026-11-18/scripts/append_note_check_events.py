"""Bind completed notes and contextual background to honestly scoped check events.

This script records primary assessments supplied in the completed inputs. It
does not prove mathematics or infer a stronger checking type from note prose.
"""
from pathlib import Path
import argparse,collections,csv,hashlib,json

p=argparse.ArgumentParser()
p.add_argument('--root',default='TOHOKU_CHECK')
p.add_argument('--utc',required=True)
a=p.parse_args();root=Path(a.root)
def jl(name):return [json.loads(s) for s in (root/name).read_text().splitlines() if s.strip()]
def tsv(name):return list(csv.DictReader((root/name).open(),delimiter='\t'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
events_path=root/'CHECK_EVENTS.tsv';backup=root/'CHECK_EVENTS.before-note-bindings.tsv'
assert not backup.exists(),'Do not overwrite the pre-assembly event history.'
events=tsv('CHECK_EVENTS.tsv');before=len(events);fields=list(events[0])
existing={x['statement_id'] for x in events}
items=tsv('NOTES_ITEM_INDEX.tsv')
slips={x['note_id']:x for x in tsv('ORIGINAL_SLIP_NOTE_INDEX.tsv')}
op={x['note_id']:x for x in jl('AUTHOR_PROOF_OBLIGATIONS.jsonl')}
lw={x['note_id']:x for x in jl('LATER_WORK_NOTES.jsonl')}
prg={x['note_id']:x for x in jl('PROGRAMME_OWN_NOTES.jsonl')}
who='GPT-6 Astra; ChatGPT Pro; effort not exposed; TOHOKU second pass, primary notes assessment'
background='carried as background without fault found'
added=[]
def add(sid,outcome,kind=background):
    assert sid not in existing,sid
    row=dict(statement_id=sid,date=a.utc,who=who,type=kind,outcome=outcome)
    events.append(row);added.append(row);existing.add(sid)
for x in items:
    sid=x['note_id'];family=x['family']
    if family=='mathematical check':
        assert sid in existing,sid
        continue
    if family=='original slip':
        s=slips[sid]
        add(sid,'Editorial-note scope only: printed p. '+x['printed_page']+', '+x['statement']+'. Consolidates the scan-based correction and second-reading evidence for '+s['correction_ids']+'. The current corrected passage and French-layer justification are given in NOTES.md. Ledger old fields may describe an earlier editorial state; restoration of a printed reading is not a newly discovered original misprint. No proof of the surrounding theorem is inferred from transcription or from this note binding. Any independent mathematical check has its own statement ID and event.')
    elif family=='proof obligation':
        s=op[sid]
        links=[z for z in x['check_event_ids'].split(';') if z and z!=sid]
        add(sid,'Proof-obligation assessment: printed p. '+str(s['printed_page'])+', '+s['title']+'. Status: '+s['status']+'. The primary read the specified source fragment and assessed what its omitted or abbreviated argument requires. This event carries the claim at that stated scope; it does not assert that every listed proof requirement was proved. Related actual checks: '+('; '.join(links) or 'none separately claimed')+'. See the complete claim and proof requirements in this note.')
    elif family=='later work':
        s=lw[sid]
        add(sid,'Public-source comparison: '+s['source_locator']+'; '+s['url']+'. The primary inspected the cited statement and displayed argument, checked the locator and compared the stated hypotheses with printed p. '+str(s['printed_page'])+', '+s['statement']+'. The cited theorem and its dependencies are carried as external background, not independently certified here. Scope limitation: '+s['scope'])
    elif family=='programme proposal':
        s=prg[sid]
        add(sid,'Own proposal, not an established theorem: '+s['title']+'. Confidence: '+s['confidence']+' Reason: '+s['reason']+' The cited programme records were read as leads. No underlying Montpellier manuscript or unreported programme proof is certified by this event. Full proposal, exact locators, and scope are in NOTES.md.')
    else:raise AssertionError(family)

records=jl('notes-context-anchors-interim-03/CONTEXT_RECORDS.jsonl')+jl('context-note-additions-interim-06/ADDED_CONTEXT_RECORDS.jsonl')
record_by={r['record_id']:r for r in records}
def values(r):return {z['name']:z['value'] for z in r['fields']}
used=collections.defaultdict(set)
for r in jl('NOTE_CONTEXT_COMPARISONS.jsonl'):used[r['context_unit_id']].add(r['note_id'])
maps={values(r)['unit_id']:r for r in records if Path(r['source_file']).name=='map.csv'}
decisions={values(r)['decision_id']:r for r in records if Path(r['source_file']).name=='dec.csv'}
used_decisions=collections.defaultdict(set)
for sid in sorted(used):
    r=maps[sid];v=values(r)
    add(sid,'Context result-state entry used as background in '+', '.join(sorted(used[sid]))+'. Source: '+r['source_file']+', logical record '+str(r['logical_record'])+', physical line '+str(r['physical_line_start'])+'. The primary read the source-unit title and the current mapping rationale. Recorded disposition: '+v['disposition']+'. This records what the supplied private map reports; it is not a new verification of its private Stacks proof body, a public tag match, or every source claim. The note-specific adds/restates/differs assessments remain in NOTE_CONTEXT_COMPARISONS.jsonl.')
    if v.get('decision_id'):used_decisions[v['decision_id']].add(sid)
for sid,uids in sorted(used_decisions.items()):
    r=decisions.get(sid)
    loc=('; '+r['source_file']+', logical record '+str(r['logical_record'])) if r else ''
    add(sid,'Decision identifier carried only as provenance of the current context mapping for '+', '.join(sorted(uids))+loc+'. The mapping rationale was read and compared in the cited notes. No independent proof of the decision’s mathematical contents is claimed by this background event, and the workflow status is not a truth certificate.')
issue_ids=[]
for r in records:
    if Path(r['source_file']).name!='issues.csv':continue
    v=values(r)
    if v['unit_id'] not in used or v['issue_id'] in existing:continue
    sid=v['issue_id'];issue_ids.append(sid)
    add(sid,'Context issue carried as an earlier-run lead for '+v['unit_id']+'. Source: '+r['source_file']+', logical record '+str(r['logical_record'])+', physical line '+str(r['physical_line_start'])+'. The primary read the complete issue claim, evidence and control fields. Its recorded resolved status is not adopted as proof; the current-run comparison or counterexample is separately identified in NOTES.md and the mathematical-check events.')

for x in items:
    for sid in x['check_event_ids'].split(';'):
        assert not sid or sid in existing,('unresolved note event',x['note_id'],sid)
backup.write_bytes(events_path.read_bytes())
with events_path.open('w',newline='') as f:
    w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(events)
receipt=dict(recorded_utc=a.utc,primary=who,events_before=before,events_after=len(events),new_note_events=len(items)-203,context_unit_events=len(used),context_decision_events=len(used_decisions),context_issue_events=len(issue_ids),new_types=dict(collections.Counter(x['type'] for x in added)),notes_count=len(items),notes_sha256=sha(root/'NOTES.md'),note_index_sha256=sha(root/'NOTES_ITEM_INDEX.tsv'),comparisons_sha256=sha(root/'NOTE_CONTEXT_COMPARISONS.jsonl'),before_sha256=sha(backup),after_sha256=sha(events_path),scope='No newly inferred proof or computation events. All new rows are explicitly scoped background links; the original actual mathematical checks remain unchanged.')
(root/'NOTES_CHECK_EVENT_BINDING.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
