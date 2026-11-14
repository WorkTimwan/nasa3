# Methods
1. **Common scale.** Every raster is block-averaged to one analysis scale (≥ the coarsest dataset's pixel size, default 500 m),
   so a 90 m Earth DEM and a ~540 m Moon map are compared at the same ground sampling.
2. **Slope.** DEMs: finite-difference slope with per-row metric pixel size (longitude shrink with cos φ). Slope maps: used directly.
3. **Window features (default 10 km):** mean slope, slope std (roughness), flat fraction (<5°), steep fraction (>15°),
   structure-tensor coherence (lineated vs isotropic fabric), edge density (scarps, rims); DEM-only: local relief.
4. **Query.** Mean feature vector inside the query disk (radius km, great-circle distance).
5. **Similarity.** Features robustly scaled (pooled median/IQR across all bodies), weighted RMS distance d,
   similarity = exp(−d²/2). Top-N % pixels are labelled into connected regions; regions below the minimum area are dropped.
6. **Site ranking.** Region score = mean similarity (blended with suitability by `suit_weight`) × small log-area bonus.
   Centroids use similarity-weighted spherical means.
7. **Suitability.** 0.3·(1−slope/12°) + 0.3·flat fraction + 0.2·(1−steep/0.25) + 0.2·(1−slope std/8°).
Validation tests: coordinate round-trips, slope of a known 10° plane, self-similarity of a query location.
