"""Database of unit cells in the ABINIT format."""
from __future__ import division, print_function

from abipy.core.structure import Structure

__all__ = [
    "ucell_names",
    "ucell",
    "structure_from_ucell",
]


def ucell_names():
    return list(_UCELLS.keys())


def ucell(name):
    return _UCELLS[name].copy()


def structure_from_ucell(name):
    return Structure.from_abivars(ucell(name))


_UCELLS = {
    "silicon": dict(ntypat=1,         
                    natom=2,           
                    typat=[1, 1],
                    znucl=14,         
                    acell=3*[10.217],
                    rprim=[[0.0,  0.5,  0.5],   # FCC primitive vectors (to be scaled by acell)
                           [0.5,  0.0,  0.5],  
                           [0.5,  0.5,  0.0]],
                    xred=[ [0.0 , 0.0 , 0.0],
                           [0.25, 0.25, 0.25]],
                    ),

    "zno": dict(ntypat=2,
                natom=2,
                typat=[1, 2],
                acell= 3*[8.6277],
                rprim= [[.0, .5, .5], [.5, .0, .5], [.5, .5, .0]],
                znucl=[30, 8],
                xred=[[.0, .0, .0], [.25,.25,.25]],
    )
}