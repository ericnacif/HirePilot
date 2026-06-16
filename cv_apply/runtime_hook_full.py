"""Runtime hook PyInstaller — variante Completa (LinkedIn/InfoJobs)."""

import os

from cv_apply.frozen_compat import apply_frozen_patches

apply_frozen_patches()
os.environ["HIREPILOT_FULL"] = "1"
