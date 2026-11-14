"""Image rendering helpers (PNG bytes) shared by the CLI and the web server."""
import io

import numpy as np
from matplotlib import colormaps
from PIL import Image


def _png(rgba):
    b = io.BytesIO()
    Image.fromarray(rgba).save(b, "PNG")
    return b.getvalue()


def base_png(stack):
    s = stack.cube[..., stack.names.index("slope_mean")]
    v = np.clip(s / 20.0, 0, 1)
    rgba = (colormaps["gray_r"](v) * 255).astype("uint8")
    rgba[~np.isfinite(s)] = (0, 0, 0, 0)
    return _png(rgba)


def overlay_png(sim, thr=None, cmap="inferno", field=None):
    a = sim if field is None else field
    v = np.clip(np.nan_to_num(a, nan=0.0), 0, 1)
    rgba = (colormaps[cmap](v) * 255).astype("uint8")
    alpha = np.where(np.isfinite(a), np.clip((v - (thr if thr is not None else 0.0)) / 0.3, 0, 1) * 200, 0)
    rgba[..., 3] = alpha.astype("uint8")
    return _png(rgba)
