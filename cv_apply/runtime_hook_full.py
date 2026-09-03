"""Runtime hook PyInstaller — variante Completa (LinkedIn/InfoJobs)."""

import os

from cv_apply.frozen_compat import apply_frozen_patches

apply_frozen_patches()
os.environ["VAGA_EM_VISTA_FULL"] = "1"
os.environ["HIREPILOT_FULL"] = "1"
