import os
import sys




class Application:

    def __init__( self,
                 application,
                 *,
                 software,
                 method,
                 extension=None,):
        
        self.applcation = application
        self.software   = software
        self.method     = method
        self.extension  = extension


    # Fonction qui est appelé lors de l'exécution
    def resolve(self,):
        ...





