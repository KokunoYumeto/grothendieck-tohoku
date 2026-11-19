from pathlib import Path
import json

root=Path('TOHOKU_CHECK')
out=[]
def add(n,page,statement,title,proposal,confidence,reason,context,relation,terms,anchors):
    out.append(dict(note_id=f'PRG-{n:02d}',printed_page=page,statement=statement,title=title,
       author='Own proposal of GPT-6 Astra in this run; no claim of historical or mathematical novelty',
       proposal=proposal,confidence=confidence,reason=reason,context_locators=context,
       context_relation=relation,context_search_terms=terms,context_anchor_ids=anchors,
       check_scope='Research or editorial proposal, not an established new theorem. Context reports are leads, and the underlying archive manuscripts were not consulted in this notes phase.'))

add(1,135,'Proposition 1.9.2; compare §3.6, p. 169','Carry diagram generators into the derivator comparison',
'For the Book VI companion, place the corrected free-diagram generator construction beside the need for coherent diagrams in derived constructions. Record separately the category of diagrams before deriving and the category of diagrams in a derived category. Start with the one-arrow counterexample and the exact evaluation adjoints for a small poset; require an explicit comparison before passing to more general shapes.',
'High for the usefulness of the distinction; medium for the proposed companion placement.',
'The p. 135 counterexample and the p. 169 repair are concrete checks. The programme’s derivator theme makes the distinction relevant, but no equivalence between those two diagram categories has been established here.',
['programme/montpellier_manuscripts.html, Book VI, physical lines 200–210', 'programme/montpellier_manuscripts.html, DATA.rows logical record 94, cote 105, physical line 494', 'stacks/tohoku_r71/issues.csv, I000004–I000006', 'stacks/tohoku_r71/map.csv, tohoku:construction:diagram-category-resolution'],
'Adds a cross-book route. The supplied material already records the bad epsilon-generator and the repaired poset construction; this proposal restates those checked ingredients and suggests a new annotation link.',
['diagram','derivators','Pursuing Stacks','105','generator'],['tohoku:prop:1.9.2','tohoku:construction:diagram-category-resolution'])
add(2,148,'Theorem 2.4.1, Remark 2; compare Proposition 3.6.2 and Lemmas 5.5.1–5.5.2','Use one explicit definition of acyclicity at degree zero',
'Build a short reusable note for all companion volumes distinguishing vanishing of positive derived functors from the stronger requirement that F(M) map isomorphically to RF(M) in every degree. Test every acyclic-resolution substitution against this definition. The additive functor A ↦ A/2A supplies a small diagnostic example; left exactness is a sufficient way to settle its degree-zero comparison.',
'High.',
'The counterexample on p. 148 is explicit, while the supplied r71 map already imposes a full degree-zero comparison at p. 169 and in the repaired p. 207 lemmas. The proposal unifies these independently located scope checks.',
['stacks/tohoku_r71/map.csv, logical records 799, 770, and 636', 'programme/montpellier_manuscripts.html, Book VI, physical lines 200–210'],
'Restates the context’s stronger p. 169 and p. 207 formulations and adds their application to Remark 2 on p. 148. It does not refute the main composition theorem.',
['acyclic','degree-zero','derived','Leray'],['tohoku:remark:2.4.1:2','tohoku:proposition:3.6.2','tohoku:lemma:5.5.1'])
add(3,220,'§5.7, formulas (5.7.6)–(5.7.7 bis)','Separate the three support and finiteness questions',
'Organize the support-cohomology companion around three separate questions: whether extension by zero of an injective is acyclic for the invariant section functor; whether the ordinary support comparison is available; and whether group cohomology commutes with the filtered colimit. As a further test, examine finite generation of the terms in a projective resolution of the trivial group module, rather than using finiteness of the group as the only criterion. No exact converse or optimal finiteness criterion is asserted here.',
'High for separating the three questions; medium for the proposed broader finiteness project.',
'The supplied issue I000030 already separates the first two gates. This run adds an explicit infinite-group obstruction to the unrestricted composite spectral sequence. A degreewise finite projective model is a plausible sufficient test because its Hom functors commute with filtered colimits; the optimal scope still needs a separate proof.',
['stacks/tohoku_r71/issues.csv, I000030', 'stacks/tohoku_r71/map.csv, logical record 97', 'programme/montpellier_manuscripts.html, Book II, physical lines 137–149; Book VI, lines 200–210'],
'Restates the context’s hypothesis separation, adds the checked counterexample, and proposes a bounded finiteness extension.',
['supports','filtered','group cohomology','finiteness','extension by zero'],['tohoku:comparison:cohomology-and-filtered-limit','tohoku:construction:extension-by-zero-support-limit'])
add(4,161,'Proposition 3.4.1; §§3.4 and 5.5','Tag every lifting problem by its topology and its band',
'In the Book I torsor and descent material, annotate each lifting statement with the topology in which local triviality is assumed and with the acting or band sheaf. Use the Zariski PGL-to-GL lift here as the first example, then keep any proposed étale, flat, or nonabelian higher-cohomology variant as a distinct statement. For Book III, this provides an organizational connection to equivariant torsors; it supplies no reconstruction theorem for the Galois tower.',
'High for the topology and band distinction; low for any stronger link to the open reconstruction questions.',
'The verified obstruction construction depends on the actual torsor topology. The supplied context already explicitly excludes a general Brauer-vanishing claim from its Proposition 3.4.1 mapping.',
['programme/montpellier_manuscripts.html, Book I, lines 121–131; Book III, lines 153–166', 'stacks/tohoku_r71/map.csv, logical record 760 and tohoku:interpretation:g-a-bundles'],
'Restates the context’s bounded Zariski interpretation and adds a proposed common annotation convention for two books.',
['torsor','PGL','descent','Galois','topology'],['tohoku:prop:3.4.1','tohoku:interpretation:g-a-bundles'])
add(5,165,'§3.4, logarithmic-derivative remark; continuation p. 166','Keep connection existence and integrability separate',
'For the Book II de Rham and crystal cluster, link the logarithmic-derivative class to two successive questions: existence of a holomorphic connection and vanishing of its curvature. Compare this distinction with the universal-vector-extension and divided-power de Rham dossiers once their actual passages are read. On curves the curvature obstruction disappears for degree reasons; in higher dimension the first obstruction alone must not be used as a flatness certificate.',
'High for the two-obstruction distinction; medium for the proposed archive comparison.',
'The paper and the supplied map distinguish a holomorphic connection from an integrable one. The programme identifies relevant de Rham dossiers, but their contents have not been checked in this run.',
['stacks/tohoku_r71/map.csv, logical records 259 and 805', 'programme/montpellier_manuscripts.html, Book II, lines 137–149', 'programme/montpellier_manuscripts.html, DATA.rows logical records 6, 49, and 130 (cotes 7, 54, and 136), line 494'],
'Restates the context’s connection-versus-integrability distinction and adds explicit proposed links to named archive dossiers.',
['connection','curvature','de Rham','crystals','54','136'],['tohoku:def:adjoint-obstruction-class','tohoku:remark:3.4.2:3:p2'])
add(6,177,'§3.8, degree-two comparison; §3.9 trace axioms','Retain small countermodels as part of the topology programme',
'Keep the finite-poset cochain certificate for the missing p. 177 transgression and the cross-cover counterexample as regression examples for any future rewrite of covering criteria. For Book V, test proposed statements about stratified covers on finite models before transferring them to geometric spaces. Treat this as a test strategy; it proves no assertion about tame stratifications or the mobility conjecture.',
'High for the countermodels as regression examples; low for their predictive value for the open geometric conjectures.',
'The examples distinguish a false terminal zero and an omitted cross-cover quantifier by direct calculations. The programme lists stratified spaces and topoi, but thematic overlap alone cannot establish a theorem about those manuscripts.',
['stacks/tohoku_r71/map.csv, logical record 425', 'stacks/tohoku_r71/issues.csv, I000031', 'programme/montpellier_manuscripts.html, Book V, lines 183–195', 'programme/montpellier_manuscripts.html, DATA.rows logical records 147–149 (cotes 150–152), line 494'],
'Adds the explicit computed p. 177 witness, restates the context’s cross-cover repair, and proposes a limited testing connection to Book V.',
['finite','Cech','stratified','topos','150','151','152'],['tohoku:eq:cech-H2-comparison-exact-sequence','tohoku:theorem:3.9.1'])
add(7,188,'Theorem 4.2.1; compare Introduction II(a)','Trace Ext comparisons into the Fourier and duality dossiers',
'Use the local-to-global Ext spectral sequence and derived adjunction as a common set of prerequisites for the Book I duality plan and Book II Fourier-transform dossier. Before asserting an inversion or base-change formula, list the kernel, support, boundedness, and properness hypotheses and verify the relevant derived comparison. The programme’s summary of cote 47 is a lead to inspect, not proof of such a formula.',
'High for the prerequisite connection; medium for the usefulness of a unified companion treatment.',
'The paper supplies the Ext and composition mechanisms; the later primary-source notes give precise modern counterparts. The supplied catalogue identifies convolution and Fourier transform on abelian varieties, but no manuscript theorem from that dossier was checked here.',
['programme/montpellier_manuscripts.html, Book I, lines 121–131; Book II, lines 137–149', 'programme/montpellier_manuscripts.html, DATA.rows logical record 42 (cote 47), line 494', 'stacks/tohoku_r71/map.csv, tohoku:theorem:4.2.1'],
'Adds a proposed dependency route between existing programme entries; it does not add a verified Fourier theorem.',
['Ext','duality','Fourier','convolution','47'],['tohoku:theorem:4.2.1','tohoku:introduction:II:a'])
add(8,119,'Whole paper, pp. 119–183 and 185–221','Keep textual fidelity and mathematical status independently visible',
'For the programme’s editions, retain separate statuses for an exact scan reading, a justified corrected reading, a proof obligation, an actual proof check, and a counterexample. Keep the refined statement ID next to every refutation. A closed mapping issue or a non-gap classification should not silently upgrade the mathematical status of all of its descendants.',
'High.',
'The supplied issue history includes both genuine source slips and invalid earlier editorial corrections. This run likewise withdrew draft suspicions, preserved proof gaps as gaps, and recorded explicit refutations separately from typography checks. Those are concrete reasons to keep the states separate.',
['stacks/tohoku_r71/issues.csv, I000022 and I000033', 'stacks/tohoku_r71/STATUS.md; stacks/MAP.md', 'programme/PROGRAMME_STATUS_20261117.md; programme/montpellier_manuscripts.html, physical lines 95–110'],
'Restates the programme’s layered-edition aim and adds a proposed check-event discipline. It does not reclassify the supplied private results state in place.',
['correction','proof','source','second pass','quality'],['tohoku:paper','tohoku:remark:ext-center-modules'])
(root/'PROGRAMME_OWN_NOTES.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in out))
print('wrote',len(out),'programme proposals')
