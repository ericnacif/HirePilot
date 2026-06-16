"""Garante que a raiz do projeto esteja no sys.path para os testes.

Permite ``import cv_apply`` independentemente do diretório de execução do pytest.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
