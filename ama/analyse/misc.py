#!/usr/bin/env python3
import os

import ase

import numpy as np


###############################################################################


def dichotomy( lenght, iter=4):
    """
    Create a list of values from 0 to lenght with a dichotomy method.
    Args:
        lenght: length of the list
        iter: number of iterations
    Returns:
        list: list of values
    """
    assert iter>0, ValueError("iter need to be a positive integer")
    assert lenght>0, ValueError("lenght need to be a positive integer")

    tab = []

    for i in range(iter):
        prev = lenght
        lenght = lenght / 2

        for h in range(2**(i)):
            tab.append( int(lenght + h*prev) )

    return np.array(tab)








