"""Exact F_2 certificate for the omitted transgression on printed p.177.

X is the finite Alexandrov space of subsets of {0,...,4} of sizes 1,3,4,
ordered by inclusion; opens are upper sets. The coefficient sheaf is constant
F_2. The five minimal opens form a finest covering. All proper nonempty
intersections are connected. Their nerve is the boundary of a 4-simplex.
Sheaf cohomology of a constant sheaf on this finite poset is computed by its
order complex (the usual augmented chain resolution is stalkwise contractible).
No floating-point rank calculation is used.
"""
from itertools import combinations
import json

def rank2(cols):
    pivots={}
    for col in cols:
        while col:
            k=col.bit_length()-1
            if k not in pivots:
                pivots[k]=col
                break
            col^=pivots[k]
    return len(pivots)

def betti(simplices):
    ranks=[0]
    for d in range(1,len(simplices)):
        rows={s:i for i,s in enumerate(simplices[d-1])}
        ranks.append(rank2([sum(1<<rows[s[:j]+s[j+1:]] for j in range(len(s))) for s in simplices[d]]))
    ranks.append(0)
    return [len(simplices[d])-ranks[d]-ranks[d+1] for d in range(len(simplices))]

def order_complex(points):
    pts=sorted(points,key=lambda x:(len(x),tuple(sorted(x))))
    return [[c for c in combinations(range(len(pts)),d+1)
             if all(pts[c[j]] < pts[c[j+1]] for j in range(d))]
            for d in range(5)]

def main():
    ground=range(5)
    points=[frozenset(s) for k in (1,3,4) for s in combinations(ground,k)]
    intersections=[]
    for k in range(1,6):
        bs=[betti(order_complex([t for t in points if frozenset(s)<=t])) for s in combinations(ground,k)]
        assert len({tuple(b) for b in bs})==1
        intersections.append({'number_of_opens':k,'count':len(bs),'betti_per_intersection':bs[0]})
    nerve=[[c for c in combinations(ground,d+1)] if d<4 else [] for d in range(5)]
    global_b=betti(order_complex(points));cech_b=betti(nerve)
    assert global_b==[1,0,9,0,0]
    assert cech_b==[1,0,0,1,0]
    assert [a['betti_per_intersection'][1] for a in intersections]==[0,1,0,0,0]
    # H^1 presheaf: zero on single opens and triple/higher intersections,
    # F_2 on each of ten pair intersections. Hence Čech H^1 has dimension 10.
    result={'field':'F_2','points':20,'poset_ranks':[1,3,4],
            'derived_cohomology_dimensions':global_b,
            'cech_cohomology_dimensions':cech_b,
            'intersection_cohomology':intersections,
            'cech_H1_of_H1_presheaf_dimension':10,
            'printed_short_exact_dimensions':[0,0,9,10,0],
            'corrected_transgression_dimensions':[0,0,9,10,1,0],
            'conclusion':'The printed terminal zero is false. A transgression to Čech H^3(X,F) is required.'}
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
