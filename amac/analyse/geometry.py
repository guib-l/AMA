#!/usr/bin/env python3
import os

import ase

import numpy as np

from scipy.spatial import distance_matrix



###############################################################################
# - Atomics distances ---------------------------------------------------------

def define_fragments(
        images:ase.Atoms, 
        fragments=[]):
    
    frags = []
    n_tot = 0
    for f in range(len(fragments)):

        frags.append(
            images[n_tot:n_tot+fragments[f]]
        )
        n_tot += fragments[f]

    return frags


def distances_com(
        fragments:list,):
    X = np.array([
        f.get_center_of_mass() for f in fragments if isinstance(f,ase.Atoms) 
    ])
    dist = distance_matrix(X,X)
    return dist


def check_distances_fragments(
        distances:np.ndarray,
        trigger_max:float=np.inf,
        strict_trigger_max=np.inf,
        trigger_min:float=0.00, ):
    
    _distances = distances.copy()
    _distances += np.eye(*distances.shape)*trigger_max

    for dist in _distances:
        
        if np.all(dist>=trigger_max):
            return False
        
        if np.any(dist>=strict_trigger_max):
            return False
        
    _distances = distances.copy()
    _distances += np.eye(*distances.shape)*trigger_min

    for dist in _distances:
        
        if np.any(dist<trigger_min):
            return False
        
    return True








def check_distances( 
        atoms:ase.Atoms, 
        criteria:dict={"C-H":1.5,}, 
        plot=True ) -> bool:
    """
    Check if the distance between atoms in the Atoms object is within 
    the criteria
    
    Args:
        atoms: Atoms object
        criteria: dictionary of criteria
    Returns:
        bool: True if the criteria is met, False otherwise

    Exemple:
    
    >>> atom = Atoms("H2",positions=[[0.,0.,0.],[0.,0.,0.8]])
    >>> assert check_distances(atom, {"H-H":0.5,}, plot=False), ValueError

    """
    
    X = atoms.positions
    dist_sq = distance_matrix(X,X)
    symbols = atoms.get_chemical_symbols()

    for j,(s1,d1) in enumerate(zip(symbols,dist_sq)):

        for k,(s2,d2) in enumerate(zip(symbols,d1)):
            if j==k:continue

            for key,item in criteria.items():
                val = key.split("-")
            
                if val[0]==s1 and val[1]==s2 and d2<=item:
                    if plot:print( " > Atoms index : %s - %s ; %s - %s"%(j,k,s1,s2) )
                    return True
            
                if val[0]==s2 and val[1]==s1 and d2<=item:
                    if plot:print( " > Atoms index : %s - %s ; %s - %s"%(j,k,s1,s2) )
                    return True            
    return False

def _distance_matrix( atoms:ase.Atoms, index:int=None )->np.ndarray:
    """
    Compute the distance matrix of the Atoms object
    Args:
        atoms: Atoms object
        index: index of the atom to get the distance from
    Returns:
        np.ndarray: distance matrix    
    """
    X = atoms.positions
    dist_sq = distance_matrix(X,X)

    if index is not None:
        return dist_sq[index]
    return dist_sq

def closest_distance(atoms:ase.Atoms, atoms_ref=(), atoms_target=()):

    dist_matrix = _distance_matrix(atoms)

    min_dist = 1000
    min_dist_index = [None,None]
    
    for r in atoms_ref:
        for t in atoms_target:
            if min_dist > dist_matrix[r][t]:
                min_dist = dist_matrix[r][t]
                min_dist_index = [r,t]

    return min_dist,min_dist_index














