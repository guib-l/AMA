import os
import sys

from amac.engine import apps 








class single_point(apps.Application):

    __NAME__ = "SP"

    def __init__(
            self,
            **kwargs):
        
        super().__init__(**kwargs)

    def resolve(self, molecule, **kwargs):
        pass









