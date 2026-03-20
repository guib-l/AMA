import os
import sys

from typing import Dict, Any




class AMAC:

    def __init__(
            self,
            *,
            method,
            software,
            application,
            **kwargs):
        
        self.method = method
        self.software = software
        self.application = application


    def compose_input(self, user_values: Dict[str, Any]) -> str:
        if not hasattr(self.software, "input_composer"):
            raise ValueError(f"Software {self.software.name} does not have an input composer defined.")
        
        composer = self.software.input_composer
        return composer.build(user_values)

    def parse_output(self, output_data: str) -> Dict[str, Any]:
        if not hasattr(self.software, "output_parser"):
            raise ValueError(f"Software {self.software.name} does not have an output parser defined.")
        
        parser = self.software.output_parser
        return parser.read(output_data)


    def handler_properties(self, *properties):
        self.properties = properties


    def execute(self, geometry):
        # 1. Compose the input file
        input_data = self.compose_input({
            "method": self.method,
            "geometry": geometry,
        })

        # 2. Run the software (this is a placeholder, actual implementation needed)
        output_data = self.software.run(input_data)

        # 3. Parse the output
        results = self.parse_output(output_data)

        # 4. Extract requested properties
        extracted_properties = {prop: results.get(prop) for prop in self.properties}
        return extracted_properties


