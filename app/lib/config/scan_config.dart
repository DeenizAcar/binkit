/// Tunable thresholds for the scan flow.
///
/// Privacy-related values (plate rejection, masking) are part of the
/// project's privacy rules; loosening them needs an explicit decision.
class ScanConfig {
  const ScanConfig({
    this.maxPlateAreaRatio = 0.15,
    this.plateScoreThreshold = 0.4,
    this.plateMaskMargin = 0.15,
    this.minConfidence = 0.6,
    this.topK = 3,
  });

  /// Reject the scan when detected plates cover more than this fraction
  /// of the frame. Privacy rule: default 15%.
  final double maxPlateAreaRatio;

  /// Minimum detector score for a box to count as a plate. Kept low on
  /// purpose: masking a false positive is harmless, missing a plate is not.
  final double plateScoreThreshold;

  /// Extra margin added around each plate box before masking, as a
  /// fraction of the box size on each side.
  final double plateMaskMargin;

  /// Below this top-1 confidence the app says "not sure" instead of
  /// guessing.
  final double minConfidence;

  /// Number of predictions returned by the classifier.
  final int topK;
}
