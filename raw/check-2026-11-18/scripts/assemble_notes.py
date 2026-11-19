"""Assemble primary-authored notes and exact evidence; make no mathematical verdicts."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,re

parser=argparse.ArgumentParser()
parser.add_argument('--root',default='TOHOKU_CHECK')
parser.add_argument('--supplement',required=True)
args=parser.parse_args()
root=Path(args.root)
supp=root/args.supplement
base=root/'notes-context-anchors-interim-03'
def jl(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def tsv(p): return list(csv.DictReader(p.open(),delimiter='\t'))
def put_tsv(p,rows,fields):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

op=jl(root/'AUTHOR_PROOF_OBLIGATIONS.jsonl')
# Primary cross-links added after the underlying fragment assessments. The
# immutable input/search snapshot is preserved; these are navigation bindings.
op_event_links={
 'OP-P132-0001':['TOH-P132-ring-diagram-relations'],
 'OP-P148-0003':['TOH-P148-remark2-positive-acyclicity-only','TOH-P148-remark2-qualified'],
 'OP-P158-0002':['TOH-P158-L3.3.1-acyclic-class'],
 'OP-P159-0001':['TOH-P159-product-sets-unqualified','TOH-N-P159-product-nonempty'],
 'OP-P168-0001':['TOH-P168-gcd-domain','TOH-N-P168-gcd-domain'],
}
for x in op:
    x['related_check_event_ids']=list(dict.fromkeys(x['related_check_event_ids']+op_event_links.get(x['note_id'],[])))
slinputs=jl(root/'ORIGINAL_SLIP_NOTE_INPUTS.jsonl')
mathinputs={x['note_id']:x for x in jl(root/'MATHEMATICAL_NOTE_INPUTS.jsonl')}
mathcontext={x['note_id']:x for x in jl(root/'MATHEMATICAL_NOTE_CONTEXT_SELECTION.jsonl')}
lw=jl(root/'LATER_WORK_NOTES.jsonl');prg=jl(root/'PROGRAMME_OWN_NOTES.jsonl')
events=tsv(root/'CHECK_EVENTS.tsv')
evby=collections.defaultdict(list)
for i,x in enumerate(events,1):
    if x['statement_id'] in mathinputs:evby[x['statement_id']].append((i,x))
rec={x['record_id']:x for x in jl(base/'CONTEXT_RECORDS.jsonl')+jl(supp/'ADDED_CONTEXT_RECORDS.jsonl')}
def fields(x):return {f['name']:f['value'] for f in x['fields']}
maps={fields(x)['unit_id']:(x,fields(x)) for x in rec.values() if Path(x['source_file']).name=='map.csv'}
units={fields(x)['id']:(x,fields(x)) for x in rec.values() if Path(x['source_file']).name=='units.csv'}
issues=collections.defaultdict(list)
for x in rec.values():
    if Path(x['source_file']).name=='issues.csv':issues[fields(x)['unit_id']].append((x,fields(x)))
bind=collections.defaultdict(list)
for x in tsv(base/'NOTE_CONTEXT_BINDINGS.tsv')+tsv(supp/'ADDED_NOTE_CONTEXT_BINDINGS.tsv'):
    if x['context_role']=='map':bind[x['note_id']].append(x)
sourcebind=collections.defaultdict(list)
for x in tsv(base/'SOURCE_ANCHOR_BINDINGS.tsv'):sourcebind[x['note_id']].append(x)

# Explicit primary comparisons, written after the map titles/rationales and issues
# were read. These constrain the generic editorial/proof-inventory descriptions.
special={
'tohoku:section:1.9':'The context already indexes the generator and set-of-subobjects discussion. This run adds the explicit pullback argument for the abelian setting and separates it from the unrestricted categorical assertion, which need not hold without further hypotheses.',
'tohoku:prop:1.9.2':'Restates the defect already recorded in I000004–I000006: the epsilon objects do not generate even for a one-arrow diagram. The present check supplies its own argument and distinguishes the repaired free-diagram construction from the printed one.',
'tohoku:prop:1.9.2:proof':'Restates I000005: naturality imposes conditions on a map from an epsilon object, so the claimed unrestricted Hom identification is false. The free-path left adjoint is a separate repaired construction.',
'tohoku:thm:1.10.1:construction:transfinite:p2':'The context explicitly uses sufficiently large cofinality. This check adds the finite-cardinal edge case and keeps that cofinality condition explicit; it does not reject the transfinite injective-embedding theorem.',
'tohoku:prop:2.2.1':'Restates the variance-sensitive repair already recorded in I000027. The present opposite-category check explains why contravariance exchanges effacement with co-effacement and injective with projective hypotheses.',
'tohoku:thm:2.2.2:dual':'Restates the halfwise-universality boundary in I000029 and the current map. The independent counterexample concerns global initial universality, not the existence of the two satellite halves. Negative co-effaceability is restricted to strictly negative degrees.',
'tohoku:example:ext-bifunctor':'The related context issue I000009 already excludes the unconditional absence of projectives: on one point the sheaf category is a module category. The present check restates that counterexample; it does not classify when arbitrary sheaf categories have enough projectives.',
'tohoku:def:associated-graded':'The context already records the indexing inconsistency and the non-uniqueness of an editorial reindexing convention (I000010). This run checks the displayed convention and its kernels and cokernels rather than declaring every other coherent convention wrong.',
'tohoku:remark:2.4.1:2':'Adds an explicit degree-zero qualification. The map invokes Leray acyclicity, but for merely additive F, positive-degree vanishing alone does not identify F with R^0F on resolution terms. The counterexample F(A)=A/2A is in TOH-P148-remark2-positive-acyclicity-only. The supplied map already recognizes the same full-acyclicity distinction at Proposition 3.6.2 (record 770) and Lemma 5.5.1 (record 636).',
'tohoku:thm:2.4.1':'The private map reports coverage for additive F and left exact G. The public primary source inspected in LW-03 assumes both functors left exact. Those are different scopes; the main printed theorem is not refuted by the separate acyclic-resolution qualification.',
'tohoku:def:flasque-and-soft-sheaves':'Adds the explicit empty-factor boundary for arbitrary sheaves of sets. The context pointwise-envelope unit already states the corresponding restriction. The nonempty-factor projection argument checks flasqueness; it is not by itself a proof of extension from arbitrary closed subsets or of every softness assertion.',
'tohoku:construction:gcd-refinement':'Adds the domain qualification x in the union of the generating open sets. Outside that union there is no selected generator through x; the subgroup there is zero. The finite gcd refinement on the union is unchanged.',
'tohoku:proof:3.6.5:p1':'Adds the distinction between a dimension-zero Noetherian space and its finite discrete T0 quotient. The printed discreteness sentence fails for a nontrivial indiscrete space; the vanishing theorem and its direct topological proof remain valid.',
'tohoku:def:ordered-zariski-example':'Adds the missing whole-space member to the family of closed initial segments. The context treats this as a source example, not as a proved external match.',
'tohoku:lemma:3.8.2':'Restates the positive-degree scope already explicit in the map rationale. Degree-zero sections need not become zero on a smaller neighborhood.',
'tohoku:eq:cech-H2-comparison-exact-sequence':'Differs from the displayed terminal zero in the indexed source formula. The finite-poset computation shows a nonzero next transgression to Čech H^3; the corrected exact-sequence continuation and the separate limits of the example are recorded in the mathematical-check notes.',
'tohoku:example:cech-H2-counterexample-construction':'Adds a needed closedness/separation qualification on the two intersection points for the source calculation. The direct finite-space test distinguishes merely having two points from having two closed points; the diagonal cokernel calculation itself is retained.',
'tohoku:theorem:3.9.1':'Restates the cross-cover trace repair already recorded in I000031 and the current map. This run adds an explicit counterexample satisfying only the printed self-trace condition and a check of the corrected induction.',
'tohoku:proposition:3.9.2':'Restates I000025 and the current map: traces of global coverings must be assigned to every relevant closed subset. The three-point example and the finite-refinement argument were checked in this run.',
'tohoku:corollary:3.10.1:2':'The context distinguishes a fundamental system of paracompact neighborhoods from its closed-subset variant using one such neighborhood. The present notes retain that distinction and add the ordinal-space counterexample to an unrestricted reading of the parenthesis.',
'tohoku:proposition:3.10.2':'The context reports a proof covering the stated topological approximation hypotheses. This run independently verifies the abelian inverse-limit and Mittag–Leffler argument only. It does not certify the complete-metrizable dense-image or nonabelian extension merely from that report.',
'tohoku:remark:proposition-3.10.2:approximation':'Restates a lead that the context itself leaves without a labelled local result. This note identifies the missing compact-neighborhood and approximation steps; no proof of the Stein application is claimed.',
'tohoku:definition:hom-o-and-local-hom':'Restates the source defect already recorded in I000032. The two-point counterexample here is independently checked, and the repaired scalar action uses sections of the center sheaf.',
'tohoku:remark:ext-center-modules':'Restates I000033 and current decision D001063: the canonical scalar ring for global Ext is the global sections of the center sheaf. Failure is already visible in degree zero. The larger center of global sections requires an additional equality hypothesis.',
'tohoku:construction:ext-restriction-maps':'Adds the explicit open-subset boundary to the use of restricted injectives. A closed-point counterexample shows that the same computation is not valid for arbitrary subsets. The context’s local Ext and modern derived-Hom references do not justify that unrestricted reading.',
'tohoku:theorem:4.2.1':'The context indexes the local-to-global Ext spectral sequence. The present proof check restates its mechanism; LW-08 additionally separates the public derived-complex version from the paper’s arbitrary noncommutative-ring scope.',
'tohoku:example:theorem-4.2.2-stalk-failure':'Adds a concrete infinite-group/convergent-sequence construction to the counterexample lead already indexed here. No finite-presentation stalk theorem is contradicted.',
'tohoku:footnote:10':'Differs from the general monomorphism claim in the indexed footnote. The two-point-to-one-point counit has a nonzero kernel. The invariant counit for an orbit quotient has a separate injectivity proof and remains valid.',
'tohoku:corollary:5.4.1':'Adds the nonemptiness qualification to the parenthetical conclusion that G is finite. Under condition (D), a point of X0 gives G equal to its finite stabilizer; the empty case does not. The cohomological assertion is unchanged in the empty case.',
'tohoku:remark:smith-fixed-point-application:p1':'Adds the separation condition needed to make the fixed locus closed in this use of the support construction. The non-Hausdorff counterexample concerns that closedness step, not a refutation of Smith theory under its usual hypotheses.',
'tohoku:lemma:5.5.1':'Restates the context’s corrected scope: either retain the intended left exactness of G, or impose strong acyclicity including the degree-zero comparison. The explicit algebraic counterexample tests the printed weaker hypothesis.',
'tohoku:lemma:5.5.2':'Restates the same strong-acyclicity repair reported in the context. Termwise derived functors and hyperderived functors must also be kept distinct. The present counterexample and corrected statement have separate check-event IDs.',
'tohoku:corollary:fixed-point-free-g-covering':'The map rationale already uses finite closed covers or locally finite closed covers on a paracompact space. The printed title is broader. This run restates that restriction and supplies the singleton-cover counterexample to unrestricted closed coverings.',
'tohoku:remark:1b-spectral-sequence-comparison':'Adds a direction check to a comparison that the context labels a remark without an exact local theorem. The canonical map goes from the second spectral sequence of Theorem 5.2.1 to the covering spectral sequence of Theorem 5.5.3.',
'tohoku:construction:fixed-point-free-refinement':'Restates I000016 and the strengthened map: both coverings must be replaced by free index sets. A fixed index cannot map equivariantly to a free one. Passing through the resulting quasi-isomorphism roof is the corrected comparison.',
'tohoku:proof:lemma-5.5.5':'Restates I000017: zero germs at finitely many points do not force a nonseparated presheaf section to vanish on their union. The corrected local argument needs individually chosen zero neighborhoods. This proof-step counterexample does not refute Lemma 5.5.5.',
'tohoku:lemma:5.5.5':'The context reports a corrected local shrinking proof and explicitly normalizes the empty open. The present notes identify the printed proof gap but do not classify the lemma itself as false.',
'tohoku:construction:product-hom-sheaf':'Restates I000020: take invariants after the orbit product, equivalently one stabilizer-fixed factor per orbit. This run also distinguishes the chosen point factor B_x from the generally larger stalk B(x) of the product sheaf.',
'tohoku:specialization:trivial-action-on-m':'Restates I000023 and the repaired map: G must act trivially on the coefficient ring as well as on M for the displayed R-module invariants formulation. The semilinear counterexample is a type obstruction, not merely a failed equality of dimensions.',
'tohoku:spectral-sequence:v':'Restates the corrected trivial-action hypothesis already recorded by the context. Sequence IV uses the skew group ring and remains a separate construction.',
'tohoku:equivalence:holomorphic-bundles-locally-free-sheaves':'Restates the analytic formulation in the map rationale. The old unit title still says algebraic; the actual setting is holomorphic bundles and coherent analytic modules. No GAGA conclusion follows without its separate hypotheses.',
'tohoku:construction:extension-by-zero-support-limit':'Restates the distinct missing-hypothesis gates already recorded in I000030. This run leaves the unrestricted derived formula as a proof gap and separately gives a counterexample to the unrestricted group-invariants composite spectral sequence; it does not turn that gap into an unproved refutation.',
'tohoku:comparison:cohomology-and-filtered-limit':'Restates the context’s separation of the group-cohomology interchange criteria from the support and acyclicity hypotheses. The explicit infinite-group counterexample is an additional check; the conditional statement retains all three kinds of requirements.',
}

comparisons=[];items=[];lines=[];missing=[];selections=[]
def emit(s=''):lines.append(s)
def plain(s):return str(s).replace('\r','').strip()
def fenced(s):return '```tex\n'+plain(s)+'\n```'
def selected(nid,page):
    uniq={b['selected_unit_id']:b for b in bind.get(nid,[]) if b['selected_unit_id'] in maps}
    def score(pair):
        uid,b=pair;x,f=maps[uid]
        pgs=re.findall(r'\d{3}',f.get('item',''))
        direct='parent' not in b['join_basis'].lower()
        specific=':section:' not in uid and ':chapter:' not in uid and uid!='tohoku:paper'
        return (-int(str(page) in pgs),-int(direct),-int(specific),int(x['logical_record']))
    return [uid for uid,b in sorted(uniq.items(),key=score)[:2]]
def context(nid,page,family,query_ids=None,explicit=None):
    qids=query_ids or [nid]
    uids=explicit or list(dict.fromkeys(u for q in qids for u in selected(q,page)))[:2]
    if not uids:
        missing.append({'note_id':nid,'kind':'no context selection','queries':qids})
        return 'Context search was performed; no exact source-anchor match was selected. The absence of an exact join is not a claim that the subject is absent from the context.'
    parts=[];relations=[]
    for uid in uids:
        if uid not in maps:
            missing.append({'note_id':nid,'kind':'selected context record unavailable','unit_id':uid});continue
        x,f=maps[uid];ux,uf=units.get(uid,(None,{}))
        loc=f"`{x['source_file']}`, logical record {x['logical_record']} (physical line {x['physical_line_start']}), `{uid}`"
        s=f"**Context.** {loc}. The supplied private mapping records `{f['disposition']}`."
        if f['disposition']=='structural_only':
            s+=' This is an index of a source passage or proof component, not an independently certified theorem.'
        else:
            s+=' Its recorded rationale is: '+f['rationale']
        if issues.get(uid):
            s+=' Related issue records: '+', '.join('`'+v['issue_id']+'` (logical record '+str(z['logical_record'])+')' for z,v in issues[uid])+'.'
        if uid in special and family!='original slip':rel=special[uid]
        elif family=='original slip':rel='Adds the present scan-based reading, second-reading verdict, and local correction evidence to this indexed passage. An earlier issue or mapping may already contain the mathematical point; this note makes no claim of discovery and does not adopt a mapping disposition as a proof.'
        elif family=='proof obligation':rel='Restates the indexed source claim or formal step and adds the explicit proof requirements and scope assessment above. The context reports coverage; that report is carried as a lead, not as a proof completed in this run.'
        elif family=='later work':rel='Adds the separately inspected public primary-source locator and the scope comparison above to the context’s mapping of the original passage. A public tag and a modified private draft are not treated as interchangeable.'
        elif f['disposition']=='structural_only':rel='Adds the actual check above to this indexed source passage. No exact independent theorem-level match is claimed from a structural record.'
        else:rel='Restates the result or proof step indexed here and adds the actual check recorded above, with its stated limitations. The private mapping remains contextual evidence of earlier work rather than evidence for that proof.'
        s+='\n\n**Relation.** '+rel
        parts.append(s);relations.append(rel)
        comparisons.append({'note_id':nid,'query_ids':qids,'context_unit_id':uid,'map_logical_record':x['logical_record'],'context_record_id':x['record_id'],'relation':rel,'reviewer':'GPT-6 Astra; ChatGPT Pro; primary'})
    parts.append('**Search record.** '+', '.join('`'+x+'`' for x in qids)+f'; all-source query logs in `notes-context-anchors-interim-03` and `{args.supplement}`. The supplied `notes/` directory is absent as recorded in the context README, lines 14–16; no missing research-note contents are assumed.')
    return '\n\n'.join(parts)

emit('# Notes on the second pass of Tôhoku')
emit()
emit('These notes accompany the scan-based check of all 102 supplied printed pages: 119–183 and 185–221. They are separate from the three source layers. The page readings, correction second reading, recurrence review, final two-pass builds, and PDF review were completed before the programme and Stacks context was opened for this notes phase. The final PDFs are the `after-final-03` builds. The supplied scan remains the authority for the text; no later source has been used to decide a printed reading.')
emit()
emit('A corrected reading is not a certification of the surrounding theorem. `CHECK_EVENTS.tsv` distinguishes actual proof checks, independent arguments, computations, rechecks, background use, and refutations. A proof obligation below says what still needs proving; it does not claim that the obligation has been discharged. Likewise, the supplied private Stacks mapping is a record of earlier AI work, not an authority. Its status words and claims of closure are reported as such. Public primary sources are cited separately in the later-work notes.')
emit()
emit('The original-slip items are grouped from 488 active ledger rows: 482 French entries and six parallel English entries. Four additional English-only exact-text groups are merged here into their corresponding French items, in addition to the two cross-layer exact groups already formed by the inventory. This gives 482 principal ledger-based items; it is not a claim that the paper contains 482 distinct mathematical errors. The exact source-group IDs remain as search aliases. Many items concern a character, a cross-reference, or grammar. The 188 proof-cue assessments also include definitions, formal verifications, and passages whose proof is supplied; they are not counted as 188 missing theorems.')
emit()
emit('## Reading guide')
emit()
emit('| Part | Contents | Item count |\n| --- | --- | ---: |\n| Original slips | Corrected local text, evidence, and primary French-layer reason | 482 |\n| Proof obligations | Claim, status, and required proof steps | 188 |\n| Mathematical checks | Actual arguments and counterexamples, grouped by statement ID | 203 |\n| Later work | Inspected primary sources with exact statement locators | 10 |\n| Programme and own proposals | Explicit links, confidence, reasons, and limits | 8 |')
emit()
emit('The mathematical-check section includes qualifications at pp. 134–135, 141–148, 159, 168–171, 176–183, 185–188, 199, 206–218, and 220. The terminal zero on p. 177 has an explicit finite-poset computation; the support discussion on p. 220 separates a proof gap from a distinct counterexample. These are statement-specific outcomes, not a blanket judgment on the paper. The p. 132 ring-action suspicion was withdrawn after re-reading the additive path relations in §1.6, and the repeated degree-zero term on p. 158 was retained as valid. `NOTES_DRAFT_REVISIONS.jsonl` preserves the explicitly logged draft revisions; the source assessments and actual check events give the final scope.')
emit()
emit('TeX snippets below encode the corrected local statement in the current source. A ledger replacement may include a nonprinting macro to locate the edit. Each ledger item includes a current corrected paragraph or display with a precise source location. No wording in these notes replaces the diplomatic reading. Where a mathematical qualification has more than one possible textual repair, it is stated as a qualification to use, with its precise scope, rather than silently rewriting the original.')
emit()
emit('## 1. Original slips and corrected local statements')
emit()

inv=root/'original-slip-notes-inventory-interim-02'
groups=tsv(inv/'ORIGINAL_SLIP_EXACT_GROUPS.tsv');sr=tsv(inv/'ORIGINAL_SLIP_ROWS.tsv')
hunks={x['hunk_id']:x for x in tsv(inv/'FRENCH_REVIEW_HUNKS.tsv')}
rowby={x['correction_id']:x for x in sr};gby={x['notes_group_id']:x for x in groups}
members=collections.defaultdict(list)
for x in sr:members[x['notes_group_id']].append(x)
alias_pairs=[('R000034','R000033'),('R009842','R009836'),('R010035','R010034'),('R010199','R010198')]
alias_to={rowby[a]['notes_group_id']:rowby[b]['notes_group_id'] for a,b in alias_pairs}
aliases=collections.defaultdict(list)
for a,b in alias_to.items():aliases[b].append(a);members[b]+=members[a]
principal=[x for x in groups if x['notes_group_id'] not in alias_to]
principal.sort(key=lambda g:(int(g['printed_page']),min(int(r['ledger_record']) for r in members[g['notes_group_id']])))
perpage=collections.Counter();slindex=[]

def paragraph_at(path,start,end):
    arr=path.read_text().splitlines()
    lo=max(0,min(start-1,len(arr)-1));hi=max(lo,min(end-1,len(arr)-1))
    while lo>0 and arr[lo-1].strip() and not arr[lo].startswith('\\LayerTarget'):lo-=1
    while hi+1<len(arr) and arr[hi+1].strip() and not arr[hi+1].startswith('\\LayerTarget'):hi+=1
    # Keep the actual paragraph/display, excluding only leading full-line comments
    # and zero-width source/anchor markers from the human-readable snippet.
    block='\n'.join(x for x in arr[lo:hi+1] if not x.lstrip().startswith('%') and not re.fullmatch(r'\\(?:SourcePage|LayerTarget)\{[^}]+\}',x.strip()))
    return lo+1,hi+1,block
def corrected_blocks(frrow,gid):
    ans=[]
    manual_ranges={'R005631':(34,36),'R010589':(33,38),'R010590':(33,38),'R010954':(54,59)}
    if frrow['correction_id'] in manual_ranges:
        start,end=manual_ranges[frrow['correction_id']]
        a,b,txt=paragraph_at(root/frrow['file'],start,end)
        return [(frrow['file'],a,b,txt,'primary-bound current paragraph; overlapping earlier ledger edits retained as history')]
    refs=[x for x in re.split(r'[;,\s]+',frrow['explicit_french_hunk_references']) if x]
    for h in refs:
        if h not in hunks:continue
        z=hunks[h];start=int(z['fr_start_line'] or z['fr_boundary_after_line'] or 1);n=int(z['fr_line_count'] or 0)
        a,b,txt=paragraph_at(root/z['fr_file'],start,start+max(1,n)-1)
        if txt.strip():ans.append((z['fr_file'],a,b,txt,'French hunk '+h))
    if not ans:
        path=root/frrow['file'];s=path.read_text();needle=frrow['new']
        match=re.search(r'\s+'.join(re.escape(z) for z in re.split(r'\s+',needle.strip())),s) if needle.strip() else None
        if match:
            start=s[:match.start()].count('\n')+1;end=s[:match.end()].count('\n')+1
            a,b,txt=paragraph_at(path,start,end);ans.append((frrow['file'],a,b,txt,'current corrected replacement located with whitespace flexibility'))
        else:
            missing.append({'note_id':gid,'kind':'corrected paragraph not automatically bound','correction_id':frrow['correction_id']})
    return list(dict.fromkeys(ans))

for g in principal:
    gid=g['notes_group_id'];page=int(g['printed_page']);perpage[page]+=1;nid=f'SL-P{page}-{perpage[page]:02d}'
    mem=members[gid];fr=next(x for x in mem if x['layer']=='corrected')
    qids=[gid]+aliases[gid];rid=[x['correction_id'] for x in mem]
    title=fr['statement'] or 'unnumbered local reading'
    emit(f'### {nid} — printed p. {page}; {title}')
    emit();emit('**Place.** '+fr['line']+'. **Ledger:** '+', '.join('`'+x+'`' for x in rid)+'.')
    emit();emit('**Source state before this ledger edit** (an earlier editorial state, not necessarily the printed reading):');emit();emit(fenced(fr['old']))
    emit();emit('**Recorded replacement** (the complete final corrected passage follows):');emit();emit(fenced(fr['new']))
    if fr['correction_id']=='R005631':
        emit();emit('**Nature of this item.** This removes a previous normalization of the number 2. It restores the printed reference without a closing parenthesis; it does not identify an original misprint. The ledger’s historical kind is retained, but its old field must not be mistaken for a diplomatic quotation.')
    elif fr['correction_id']=='R010954':
        emit();emit('**Nature of this item.** This removes an added choice of orbit representative and an extra isomorphism from an earlier editorial state. The underlying original error in this passage concerns taking invariants after the orbit product. The complete corrected passage below retains that repair while restoring the printed manner of indexing the product in the following prose.')
    blocks=corrected_blocks(fr,gid)
    for file,a,b,txt,basis in blocks:
        emit();emit(f'**Corrected local statement.** `{file}`, current source lines {a}–{b} ({basis}).');emit();emit(fenced(txt))
        selections.append({'note_id':nid,'correction_id':fr['correction_id'],'source_file':file,'line_start':a,'line_end':b,'basis':basis,'sha256':hashlib.sha256(txt.encode()).hexdigest()})
    emit();emit('**Evidence and justification.** '+fr['evidence'])
    reasons=[]
    for rr in mem:
        for hid in re.split(r'[;,\s]+',rr['explicit_french_hunk_references']):
            if hid in hunks:
                z=hunks[hid];v=f"`{hid}` — {z['primary_decision']}: {z['primary_reason']}"
                if v not in reasons:reasons.append(v)
    if reasons:emit();emit('**French-layer verdict.** '+' '.join(reasons))
    emit();emit('**Second reading.** '+'; '.join(x['correction_id']+': '+x['confidence'] for x in mem)+'.')
    ens=[x for x in mem if x['layer']=='English']
    if ens:
        emit();emit('**Parallel English correction.** '+', '.join('`'+x['correction_id']+'`' for x in ens)+' is the same original item, retained with its own ledger evidence and search alias.')
    emit();emit(context(nid,page,'original slip',qids));emit()
    items.append(dict(note_id=nid,family='original slip',printed_page=page,statement=title,context_query_ids=';'.join(qids),check_event_ids=nid))
    slindex.append({'note_id':nid,'printed_page':page,'principal_source_group':gid,'source_group_aliases':';'.join(aliases[gid]),'correction_ids':';'.join(rid),'statement':title})

emit('## 2. Proof obligations and deliberately abbreviated arguments');emit()
emit('Each entry retains the primary assessment of its exact source fragment. A definition or a supplied proof is identified as such. Where an argument is still needed, the listed steps are requirements for a proof, not assertions that this run proved the whole result. Related actual checks are linked by their statement IDs.');emit()
for x in op:
    nid=x['note_id'];pg=x['printed_page']
    emit(f"### {nid} — printed p. {pg}; {x['title']}");emit()
    emit(f"**Source.** `{x['source_file']}`, lines {x['source_lines']}; fragment `{x['fragment_id']}`. **Assessment:** {x['status']}.")
    emit();emit('**Claim or formal step.** '+x['claim']);emit();emit('**What a proof needs / scope of the supplied argument.** '+x['proof_needs'])
    if x['related_check_event_ids']:emit();emit('**Actual check links.** '+', '.join('`'+a+'`' for a in x['related_check_event_ids'])+'.')
    emit();emit(context(nid,pg,'proof obligation'));emit()
    items.append(dict(note_id=nid,family='proof obligation',printed_page=pg,statement=x['title'],context_query_ids=nid,check_event_ids=';'.join([nid]+x['related_check_event_ids'])))

emit('## 3. Mathematical checks, counterexamples, and refined statements');emit()
emit('These are the outcomes actually recorded during this run, grouped by statement ID. Distinct events for the same ID remain distinct, with their dates and literal check types. A counterexample to a proof step does not automatically refute its enclosing theorem. Where a printed assertion is refuted, the outcome identifies the refined statement. The counterexample scripts and their receipts remain in the archive.');emit()
for nid,x in mathinputs.items():
    pg=x['printed_page'];m=mathcontext[nid]
    emit(f'### {nid} — printed p. {pg}');emit()
    emit('**Statement locator.** `'+nid+'`; contextual source unit `'+m['context_unit_id']+'`.')
    for row,e in evby[nid]:
        emit();emit('**Event:** '+e['type']+'; '+e['date']+'; '+e['who']+'.');emit();emit(e['outcome'])
    emit();emit(context(nid,pg,'mathematical check',explicit=[m['context_unit_id']]));emit()
    items.append(dict(note_id=nid,family='mathematical check',printed_page=pg,statement=nid,context_query_ids=nid,check_event_ids=nid))

emit('## 4. Later work: precise primary-source comparisons');emit()
emit('These references were inspected during the notes phase on 18 November 2026. They are used only for mathematical context. Each entry states the comparison and its limits; none is an alternative text witness for the French or English layers. The selection is a set of directly verified connections, not an exhaustive history of later work.');emit()
for x in lw:
    nid=x['note_id'];pg=x['printed_page'];emit(f"### {nid} — printed p. {pg}; {x['statement']}");emit()
    emit('**'+x['title']+'.** ['+x['source_locator']+']('+x['url']+').');emit();emit(x['claim']);emit()
    emit('**Relation to the paper.** '+x['relation_to_tohoku']);emit();emit('**Limits.** '+x['scope']);emit();emit('**Check scope.** '+x['check_scope'])
    emit();emit(context(nid,pg,'later work',explicit=x['context_anchor_ids']));emit()
    items.append(dict(note_id=nid,family='later work',printed_page=pg,statement=x['statement'],context_query_ids=nid,check_event_ids=nid))

emit('## 5. Programme connections and own proposals');emit()
emit('The programme catalogue and status files were supplied as leads. Their reports of completed research are not adopted as established mathematical results. No Montpellier manuscript was opened in this notes phase. The following connections are this run’s proposals; confidence concerns the stated proposal and reason, not an assertion of novelty or a proof of the programme’s open questions.');emit()
for x in prg:
    nid=x['note_id'];pg=x['printed_page'];emit(f"### {nid} — printed p. {pg}; {x['statement']}");emit()
    emit('**'+x['title']+'.** '+x['author']+'.');emit();emit(x['proposal']);emit()
    emit('**Confidence.** '+x['confidence']);emit();emit('**Reason.** '+x['reason']);emit()
    emit('**Exact programme/context locators.** '+'; '.join(x['context_locators'])+'.');emit();emit('**Adds, restates, or differs.** '+x['context_relation']);emit();emit('**Limit.** '+x['check_scope'])
    emit();emit(context(nid,pg,'programme proposal',explicit=x['context_anchor_ids']));emit()
    items.append(dict(note_id=nid,family='programme proposal',printed_page=pg,statement=x['statement'],context_query_ids=nid,check_event_ids=nid))

emit('## 6. Coverage and provenance of these notes');emit()
emit('`NOTES_ITEM_INDEX.tsv` lists every principal note and its context-query and check-event IDs. `ORIGINAL_SLIP_NOTE_INDEX.tsv` preserves all 488 original-slip ledger rows through 482 principal items and their source-group aliases. `AUTHOR_PROOF_OBLIGATIONS.jsonl` preserves all 188 fragment assessments. `NOTE_CONTEXT_COMPARISONS.jsonl` records the primary comparisons used above. The all-source search logs record exact terms, source coverage, and match locators; a literal hit is not itself a semantic match. The primary selected and read the cited context records. Structural parent nodes and contents-page markers are not treated as proofs of their descendants.')
emit()
emit('The supplied private mapping currently labels its issues resolved and its direct children non-gap. Those are statuses of that project’s mapping workflow. They do not settle every original proof obligation: examples include the p. 183 approximation extension and the p. 220 support hypotheses. The source text, the corrected statement, and the degree of checking remain separately visible here and in `CHECK_EVENTS.tsv`.')
emit()
assert len(items)==891,(len(items),collections.Counter(x['family'] for x in items))
assert len({x['note_id'] for x in items})==891
(root/'NOTES.md').write_text('\n'.join(lines)+'\n')
put_tsv(root/'NOTES_ITEM_INDEX.tsv',items,['note_id','family','printed_page','statement','context_query_ids','check_event_ids'])
put_tsv(root/'ORIGINAL_SLIP_NOTE_INDEX.tsv',slindex,['note_id','printed_page','principal_source_group','source_group_aliases','correction_ids','statement'])
(root/'NOTE_CONTEXT_COMPARISONS.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in comparisons))
(root/'NOTES_CORRECTED_PARAGRAPH_BINDINGS.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in selections))
(root/'NOTES_ASSEMBLY_ISSUES.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in missing))
print(json.dumps({'notes':len(items),'families':dict(collections.Counter(x['family'] for x in items)),'context_comparisons':len(comparisons),'source_paragraphs':len(selections),'assembly_issues':len(missing),'NOTES_bytes':(root/'NOTES.md').stat().st_size},indent=2))
for x in missing:print(json.dumps(x,ensure_ascii=False))
