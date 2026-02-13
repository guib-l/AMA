#!/usr/bin/env python3
import os
import sys
import time

import numpy as np

import typing

from amac.ios.parser import Parser

from ase import Atoms


def _similar_read_molden(filename="deMon.mol", 
                         keep:int=1, 
                         is_charged=True, 
                         is_md=False,
                         get_comment=False):
    """     
    Read a molden file and return the images as ASE Atoms objects.
    
    Parameters
    ----------
        filename : str
            The name of the molden file to read.
        keep : int or list of int
            If int, keep every `keep`-th image. If list, keep only the images
            with indices in the list.
        is_charged : bool
            If True, read the charges from the molden file. If False, set
            all charges to 0.
        get_comment : bool
            If True, return the comments from the molden file.
    
    Returns
    -------
        images : list of Atoms
            The images as ASE Atoms objects.
        comments : list of str  
            The comments from the molden file. Only returned if `get_comment`
            is True.
    """
    images = Parser( filename )
    atoms = np.array(images.data)

    nat = atoms[0,0] 
    comments = []

    lenght  = 4
    res = len(atoms) % (nat+2)

    if res != 0:
        atoms = atoms[:len(atoms) - int(res)]

    if is_charged:
        lenght += 1

    if is_md:
        lenght += 3
    atoms = atoms[:,:lenght]

    image = np.reshape( atoms, 
                ( int(len(atoms) // (nat+2)), int(nat+2), lenght ) )
    
    structures = []

    def compound( img,structures,comments, get_comment,is_charged,is_md ): 
        if get_comment:
            comments.append(img[1])

        iter_max = 3
        symb  = img[2:,0].ravel()
        pos   = img[2:,1:iter_max+1]
        chrg  = np.zeros((len(symb),))
        veloc = np.zeros(np.shape(img[2:,1:4]))

        if is_charged:
            iter_max += 1
            chrg = img[2:,iter_max].ravel()

        if is_md:
            iter_max += 1
            veloc = img[2:,iter_max:]

        atm = Atoms(symb, pos, charges=chrg, velocities=veloc)
        structures.append(atm)

        return structures,comments


    if isinstance(keep,(float,int)) :

        for i,img in enumerate(image):

            if i%keep==0.:
                structures,comments = compound( img,
                    structures,comments, get_comment,is_charged,is_md )

        if get_comment:
            return structures,comments

    if isinstance(keep,(np.ndarray,list)) :

        for i,img in enumerate(image):
            
            if i in keep:
                structures,comments = compound( img,
                    structures,comments, get_comment,is_charged,is_md )

        if get_comment:
            return structures,comments
        
    return structures

read_molden = _similar_read_molden

def _read_xyz_ext(fileobj, is_charges=True, keep=1):
    info = []
    lines = fileobj.readlines()
    if lines[0] == "\n":
        lines = lines[1:]
        
    images = []

    nbmol = 0 

    from amac.ios.utils import updateIter
    
    show = updateIter()

    
    while len(lines) > 0:

        symbols = []
        positions,charges = [],[]
        natoms = int(lines.pop(0))
        comment = lines[0]
        info.append(  comment  )
        
        lines.pop(0)  # Comment line; ignored
        
        nread = natoms
        while nread>0:

            if len(lines[0].split())==1:
                break
            line = lines.pop(0)

            if is_charges:
                symbol, x, y, z, c = line.split()[:5]
                symbol = symbol.lower().capitalize()
                symbols.append(symbol)
                positions.append([float(x), float(y), float(z)])
                charges.append( float(c) )
            else:
                symbol, x, y, z = line.split()[:4]
                symbol = symbol.lower().capitalize()
                symbols.append(symbol)
                positions.append([float(x), float(y), float(z)])
                charges.append( 0.00 )
            
            nread -= 1

        if nread==0:
            img = Atoms(symbols=symbols, positions=positions)
            img.set_initial_charges( charges )

        nbmol += 1
        show(nbmol)
        if nbmol % keep == 0:
            images.append(img)

    print(" \u2705 Loaded {} elements from XYZ file.".format(nbmol,))
    return images,np.array(info)


def _write_xyz_ext(fileobj, images, charges=None, energy=None, comment='', fmt='%22.15f'):
    """
    Write XYZ file with additional information.
    Parameters
    ----------
    fileobj : file object
        File object to write to.
    images : list of Atoms
        List of Atoms objects to write.
    charges : list of float
        List of charges for each atom in the images.
    energy : list of float, optional
        List of energies for each image. If None, no energy will be written.
    comment : str, optional
        Comment to be written in the file. Default is ''.
    fmt : str, optional
        Format string for the coordinates. Default is '%22.15f'.
    """
    
    comment = comment.rstrip()

    if '\n' in comment:
        raise ValueError('Comment line should not have line breaks.')
    
    nImg = len(images)
    if charges is None:
        charges = [None,] * nImg
    if energy is None:
        energy = [None,] * nImg

    for atoms,charge,energie in zip(images,charges,energy):
        natoms = len(atoms)
    
        if charge is None:
            charge = [0.,] * natoms

        fileobj.write('%s \n'%natoms)
        fileobj.write('energy (Ha) : %s | %s\n' % (energie, comment))
        for s, (x, y, z), c in zip(atoms.symbols, atoms.positions, charge):
            fileobj.write('%-2s %s %s %s %s\n' % (s, fmt % x, fmt % y, fmt % z, fmt % c ))

    print(" \u2705 Write {} elements in XYZ file.".format(len(images)))

def read_XYZ(filename, **kwargs):
    with open(filename,"r") as fd:
        temp = _read_xyz_ext(fd, **kwargs)
    return temp


def write_XYZ(filename, images, intent='w',**kwargs):
    if not isinstance(images,list):
        images = [images]
    with open(filename,intent) as fd:
        _write_xyz_ext(fd, images,**kwargs)
    return None


