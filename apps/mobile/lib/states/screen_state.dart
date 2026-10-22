/// The seven states every data screen implements (Part 3 section 44.2, design spec section 9).
/// This is a UI-only axis; it is separate from the data vocabulary (`display_status`,
/// `value_state`) generated from the contracts.
enum ScreenState {
  loading,
  empty,
  partial,
  undecidable,
  stale,
  error,
  changed,
}

/// Why a result changed between releases (section 44.2 "변경됨").
enum ChangeCause {
  sourceChanged('원문이 바뀌었어요'),
  processorChanged('처리 방식이 바뀌었어요');

  const ChangeCause(this.label);

  final String label;
}
