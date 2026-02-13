import os
import sys


class _unified(object):
    """Objet qui redistribut les méthodes connues vers les méthodes unifiées"""

    def __new__(cls):
        pass

    def __init__(self):
        pass

    def __getattribute__(self, name):
        pass
        
    def __setattr__(self, name, value):
        pass

    def __str__(self):
        pass



class _unified_calculator(_unified):

    def __init__(self):
        pass









