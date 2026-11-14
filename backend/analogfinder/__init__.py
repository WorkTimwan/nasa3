"""analogfinder - find terrestrial analogs for Moon/Mars station sites.

Compares terrain character (slope, roughness, structure/lineaments, relief)
across Earth, Moon and Mars rasters and ranks look-alike regions.
"""
__version__ = "0.1.0"

# Mean radii in km
BODY_RADIUS_KM = {"earth": 6371.0, "moon": 1737.4, "mars": 3389.5}
