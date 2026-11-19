from pathlib import Path
import csv,json,re

ROOT=Path('TOHOKU_CHECK')
def write(name,rows):
    (ROOT/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))

pages=json.loads((ROOT/'NOTES_PAGE_SUBJECTS.json').read_text())
event_source=ROOT/'CHECK_EVENTS.before-note-bindings.tsv'
if not event_source.exists():event_source=ROOT/'CHECK_EVENTS.tsv'
events=list(csv.DictReader(event_source.open(),delimiter='\t'))
manual={41:172,42:173,43:174,44:175,45:175,46:176,47:176,48:176,49:176,
56:179,57:179,58:179,59:180,60:180,61:180,62:181,63:181,64:181,65:182,66:182,67:183,68:183,
69:185,70:185,71:185,72:186,73:187,74:187,75:187,76:188,77:188,78:189,79:189,80:189,81:190,82:190,83:190,84:191,85:191,86:191,
97:196,98:196,99:197,101:198,102:198,103:198,106:199,107:200,108:200,109:200,
184:179,185:179,186:180,195:185,196:187}
group={}
for i,e in enumerate(events):
    sid=e['statement_id']
    m=re.search(r'(?:[Pp]|TOH)(1[2-9]\d|20\d|21\d|220|221)(?!\d)',sid)
    pg=int(m.group(1)) if m else manual.get(i)
    assert pg is not None,(i,sid)
    x=group.setdefault(sid,{'note_id':sid,'printed_page':pg,'context_search_terms':pages[str(pg)]+[sid], 'event_rows':[], 'input_kind':'primary mathematical-check note; page assigned by primary from the checked statement'})
    x['event_rows'].append(i+1)
write('MATHEMATICAL_NOTE_INPUTS.jsonl',list(group.values()))

lw=[]
def add(n,pg,st,title,locator,url,claim,relation,scope,terms,anchors):
    lw.append(dict(note_id=f'LW-{n:02d}',printed_page=pg,statement=st,title=title,source_locator=locator,url=url,claim=claim,relation_to_tohoku=relation,scope=scope,context_search_terms=terms,context_anchor_ids=anchors,source_checked_utc='2026-11-18',check_scope='Primary read the cited statement and its displayed proof or construction; the full web source and every dependency were not independently re-proved.'))

add(1,135,'Theorem 1.10.1; pp. 135–137','Functorial injective embeddings',
'The Stacks Project, Theorem 19.11.7, tag 079H','https://stacks.math.columbia.edu/tag/079H',
'An abelian category with exact filtered colimits and a generator admits a functorial monomorphism from every object into an injective object.',
'Restates and organizes the transfinite attachment argument of Theorem 1.10.1. The modern proof makes the cofinality choice explicit.',
'The functor need not be additive. A sufficiently large infinite regular cofinality is required; this does not license a finite stopping ordinal.',
['injective','generator','transfinite','079H'],['tohoku:thm:1.10.1:p1','tohoku:thm:1.10.1:construction:transfinite:p2'])
add(2,138,'§1.11; pp. 138–139','Serre quotient and its universal property',
'The Stacks Project, Lemma 12.10.6, tag 02MS; Definition 12.10.1 in tag 02MN','https://stacks.math.columbia.edu/tag/02MS',
'For a Serre subcategory, localization at morphisms whose kernels and cokernels lie in it gives an abelian quotient with an exact quotient functor and the expected exact-functor universal property.',
'Restates the quotient construction and adds an explicit universal property. Modern weak Serre corresponds to the paper’s special full-subcategory condition; modern Serre corresponds to its thick-subcategory condition.',
'Keep the size conditions required for locally small Hom sets. The quoted terminology concerns abelian categories, not the later triangulated meaning of thick.',
['Serre','quotient','weak Serre','02MS'],['tohoku:def:complete-subcategory','tohoku:def:thick-subcategory','tohoku:prop:quotient-category-properties'])
add(3,148,'Theorem 2.4.1','Modern composition spectral sequence',
'The Stacks Project, Lemmas 13.22.1–13.22.2, tags 015M–015N, in §13.22 (015L)','https://stacks.math.columbia.edu/tag/015N',
'For left exact functors F and G between abelian categories with enough injectives, with F carrying injectives to G-acyclic objects, the composition construction gives the bounded-below Grothendieck spectral sequence and a finite filtration in each total degree.',
'Uses the composition mechanism of Theorem 2.4.1. The public statement inspected imposes left exactness on F as well as G; the printed theorem allows additive F. Thus it is not an exact scope match.',
'The private r71 map reports a broader additive-F treatment; its report and the public tag must not be conflated. Positive-degree acyclicity alone also needs the degree-zero qualification in the separate p. 148 note.',
['composite','acyclic','spectral sequence','015N'],['tohoku:thm:2.4.1','tohoku:remark:2.4.1:2'])
add(4,147,'§2.4, unbounded-complex remark','K-injective resolutions beyond bounded-below complexes',
'The Stacks Project, Theorem 19.12.6, tag 079P','https://stacks.math.columbia.edu/tag/079P',
'Every complex in a Grothendieck abelian category has a functorial monomorphic quasi-isomorphism to a termwise injective K-injective complex.',
'Extends the resolution machinery underlying the paper’s hyperderived constructions to unbounded complexes under the Grothendieck-category hypothesis.',
'Existence of an unbounded derived functor is separate from convergence of either spectral sequence in §2.4. No unconditional convergence assertion is inferred.',
['K-injective','unbounded','Grothendieck','079P'],['tohoku:remark:derived-spectral-functor-scope'])
add(5,170,'Theorem 3.6.5; pp. 170–171','Noetherian topological cohomological dimension',
'The Stacks Project, Proposition 20.20.7, tag 02UZ','https://stacks.math.columbia.edu/tag/02UZ',
'On a Noetherian topological space of dimension at most d, the cohomology of every abelian sheaf vanishes in degrees greater than d.',
'Restates the vanishing theorem and explicitly cites Tôhoku Theorem 3.6.5. Its dimension-zero argument uses irreducibility and the absence of a proper nonempty open, without asserting that the original space is discrete.',
'This is compatible with the qualification of the printed dimension-zero sentence: pass to the topologically indistinguishable quotient, or argue directly with the topology.',
['Noetherian','dimension','vanishing','02UZ'],['tohoku:theorem:3.6.5'])
add(6,175,'Theorem 3.8.1; pp. 175–176','Čech-to-derived comparison for one covering',
'The Stacks Project, Lemma 20.11.5, tag 01ES; Lemma 20.11.6 in §20.11, tag 01EO','https://stacks.math.columbia.edu/tag/01ES',
'For an open covering of a ringed space there is a functorial spectral sequence with E2 given by Čech cohomology of the presheaves of local sheaf cohomology, converging to sheaf cohomology. Vanishing of higher cohomology on all finite intersections gives the Čech comparison isomorphism.',
'Restates and uses the paper’s covering spectral sequence. The modern proof presents it as a composition spectral sequence.',
'The statement concerns one covering and its intersections. It does not repair the separate cross-cover trace condition in §3.9 or the erroneous terminal zero of the printed p. 177 low-degree sequence.',
['Čech','Cech','covering','01ES'],['tohoku:theorem:3.8.1','tohoku:lemma:3.8.2'])
add(7,183,'Proposition 3.10.2','Derived inverse limits and the Mittag–Leffler obstruction',
'The Stacks Project, Lemmas 15.88.1 and 15.88.10, §15.88, tag 07KV','https://stacks.math.columbia.edu/tag/07KV',
'For a countable inverse system of abelian groups, derived inverse limit is represented by the two-term product complex with differential 1 minus shift, and has no derived terms above degree one. The Mittag–Leffler condition kills the first derived limit. The cited later lemma gives the cohomology short exact sequence for derived limits of complexes.',
'Extends the paper’s inverse-limit discussion into derived-category language and isolates the obstruction used in the abelian re-proof recorded here.',
'This does not establish the nonabelian assertion or the separate topological approximation remark on p. 183. Countability and the relevant Mittag–Leffler hypotheses are retained.',
['Mittag','inverse limit','derived limit','07KV'],['tohoku:proposition:3.10.2'])
add(8,188,'Theorem 4.2.1; pp. 187–190','Sheaf Ext for complexes',
'The Stacks Project, §20.43, tag 0BQP, definition and displayed local-to-global spectral sequence','https://stacks.math.columbia.edu/tag/0BQP',
'Sheaf Ext of complexes is the cohomology sheaf of derived internal Hom. It is also the sheafification of local derived Ext groups. Under the indicated boundedness conditions there is a local-to-global spectral sequence.',
'Extends the objects-and-resolutions construction in §4.2 to derived complexes.',
'Use the stated ringed-space and boundedness conventions. This citation is not a proof of the paper’s full arbitrary noncommutative-ring scope, and it does not justify restriction to arbitrary subsets.',
['Ext','internal Hom','local-to-global','0BQP'],['tohoku:theorem:4.2.1','tohoku:section:4.2'])
add(9,162,'§3.4; compare p. 213, Remark II','Torsors and first cohomology on a site',
'The Stacks Project, Lemma 21.4.3, tag 03AJ','https://stacks.math.columbia.edu/tag/03AJ',
'For an abelian sheaf on a site, first cohomology is naturally in bijection with isomorphism classes of torsors under that sheaf.',
'Extends the abelian torsor interpretation from topological spaces to sites and gives an explicit construction using an injective embedding.',
'The source itself leaves the final inverse verification to the reader. This is an H1 statement for an abelian band, not a cited classification theorem for arbitrary nonabelian H2.',
['torsor','principal','H1','03AJ'],['tohoku:comparison:cech-derived-h1','tohoku:interpretation:g-a-bundles'])
add(10,120,'Introduction II(a)','Right adjoints and the later duality framework',
'The Stacks Project, Lemma 48.3.1, tag 0A9E; §48.3, tag 0A9D','https://stacks.math.columbia.edu/tag/0A9E',
'For a morphism between quasi-compact quasi-separated schemes, derived pushforward on derived categories with quasi-coherent cohomology has a right adjoint. The proof uses compact generation and preservation of coproducts.',
'Develops the categorical and Ext-based duality direction announced in the introduction. This is a structural extension, not a claim that the paper already proves this modern theorem.',
'For a general morphism this right adjoint should not automatically be denoted f!. The cited source explicitly distinguishes that notation from the exceptional inverse image of duality theory.',
['duality','Serre','right adjoint','0A9E'],['tohoku:introduction:II:a'])
write('LATER_WORK_NOTES.jsonl',lw)
print('wrote',len(group),'mathematical inputs and',len(lw),'later-work notes')
