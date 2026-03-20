import os,sys





class _software:

    def __init__(
            self,
            *,
            name,
            version,
            input_composer,
            output_parser,
            command=None,
            use_system=False,):
        
        self.name = name
        self.version = version
        self._command = command

    def _input_composer(
            self,
            composer,
            mandatory_attr=["write"]):
        
        if hasattr(composer,mandatory_attr):
            self.input_composer = composer


    def _output_parser(
            self,
            parser,
            mandatory_attr=["read"]):
        
        if hasattr(parser,mandatory_attr):
            self.output_parser = parser




