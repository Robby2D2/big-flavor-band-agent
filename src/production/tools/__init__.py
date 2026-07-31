"""Audio-tool package.

Importing this package imports every tool module, whose ``@register`` decorator
adds it to ``toolkit.REGISTRY``. Adding a new tool = dropping a new module here
and listing it below. Import order sets the order tools are advertised in.
"""

# Order mirrors the historical list_tools() ordering.
from . import analyze_audio            # noqa: F401
from . import match_tempo              # noqa: F401
from . import correct_beats            # noqa: F401
from . import create_transition        # noqa: F401
from . import apply_mastering          # noqa: F401
from . import get_audio_cache_stats    # noqa: F401
from . import analyze_recommend        # noqa: F401  (whole-song bundled analyzer)
from . import trim_silence             # noqa: F401
from . import reduce_noise             # noqa: F401
from . import remove_hum               # noqa: F401
from . import correct_pitch            # noqa: F401
from . import normalize_audio          # noqa: F401
from . import apply_eq                 # noqa: F401
from . import remove_artifacts         # noqa: F401
from . import auto_clean               # noqa: F401  (whole-song orchestrator; must load last)
