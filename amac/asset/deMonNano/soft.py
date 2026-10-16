
import copy

from amac import config
from amac.engine.software import Software
from dataclasses import dataclass




class software_deMonNano(Software):

    name = "deMonNano"
    alias = ("demonano","demon_nano","demon-nano")
    requires_executable = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def configure(self) -> None:
        """Load and apply the software configuration."""
        _config = config.CONFIGURE[self.name]

        if self.requires_executable:
            self.execute = _config.get("EXECUTABLE",None)
            
        self.basis = _config.get("BASIS",None)
        self.environ = _config.get("ENVIRON",None)


    def collect(self):
        ...

    def callback(self):
        ...

    def prepare(self):
        ...

    def calculate(self):
        ...
    
    def run(self):
        ...






