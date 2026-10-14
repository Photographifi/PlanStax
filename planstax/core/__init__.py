from .pipeline import Cancelled, Pipeline
from .postprocess import apply_post, apply_pre, auto_balance, estimate_rgb_shifts
from .wavelets import WaveletProcessor, apply_wavelets


def finish(stacked, settings):
    """Stacked image → final image: channel alignment, wavelets, then colour/levels/orientation."""
    img = apply_pre(stacked, settings.post)
    img = apply_wavelets(img, settings.wavelet)
    return apply_post(img, settings.post)


__all__ = ["Cancelled", "Pipeline", "WaveletProcessor", "apply_post", "apply_pre",
           "apply_wavelets", "auto_balance", "estimate_rgb_shifts", "finish"]
