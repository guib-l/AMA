import os
import sys

from typing import List, Optional
from pathlib import Path

from dataclasses import dataclass

from contextlib import ExitStack
import subprocess


@dataclass
class SimpleExecute:
    # 'Gestion des erreurs' construite avec Copilot
    # Model : Claude (Opus 4.5)

    commands: List[List[str]] = None
    directory: str = "./"
    shell: bool = False
    timeout: Optional[int] = None

    def __post_init__(self):
        self.directory = Path(self.directory)
        if not self.directory.exists():
            raise ValueError(f"Directory {self.directory} does not exist")

    def _execute_command(self, cmd: List[str]) -> tuple[str, str, int]:
        """Execute a single command and return stdout, stderr, and return code."""
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=self.shell,
                #bufsize=1,
                cwd=str(self.directory)
            )
            stdout, stderr = process.communicate(timeout=self.timeout)
            return stdout, stderr, process.returncode
        
        except subprocess.TimeoutExpired:
            process.kill()
            raise RuntimeError(f"Command {cmd} timed out after {self.timeout} seconds")
        
        except Exception as e:
            raise RuntimeError(f"Failed to execute command {cmd}: {e}")

    def execute(self, commands=None) -> dict:
        """Execute all commands and return results."""
        
        if commands is None:
            commands = self.commands
        
        if isinstance(commands, list) and all(isinstance(c, str) for c in commands):
            commands = [commands,]

        results = {
            'outputs': [],
            'errors': [],
            'return_codes': [],
            'success': True
        }

        for i, cmd in enumerate(commands):
            try:
                stdout, stderr, returncode = self._execute_command(cmd)
                results['outputs'].append(stdout)
                results['errors'].append(stderr)
                results['return_codes'].append(returncode)
                
                if returncode != 0:
                    results['success'] = False
                    
            except Exception as e:
                results['outputs'].append("")
                results['errors'].append(str(e))
                results['return_codes'].append(-1)
                results['success'] = False

        return results
























