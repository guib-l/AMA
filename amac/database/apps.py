import os
import sys

from amac.engine.application import Application








class single_point(Application):

    def __init__(
            self, 
            application="SP",
            **kwargs):
        
        super().__init__(**kwargs)

    def resolve(self):
        pass




single_point(
    software="deMonNano",
    method="DFTB-2",
    extension=None,
)







