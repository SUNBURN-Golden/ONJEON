import 'package:flutter/widgets.dart';
import 'package:onjeon_contracts/onjeon_contracts.dart';

/// The three ways into the app (Part 3 section 43.4). None of them asks for a PDF,
/// family history or a consultation before the user can read coverage and source text.
enum EntryPoint {
  example('예시로 둘러보기'),
  fresh('처음부터 준비하기'),
  pdf('가입내역 PDF 올리기');

  const EntryPoint(this.label);

  final String label;
}

/// What the user chose on the way in. Nothing here is sent anywhere.
class AppSession extends ChangeNotifier {
  EntryPoint? _entry;
  final PolicyHoldingsStatus _holdings = PolicyHoldingsStatus.skipped;

  EntryPoint? get entry => _entry;

  /// Holdings stay skipped until the PDF import exists (T-MB-04); skipping is not "no insurance".
  PolicyHoldingsStatus get holdings => _holdings;

  /// True in example mode: every screen shows the example banner and the data is not real.
  bool get synthetic => _entry == EntryPoint.example;

  void enter(EntryPoint entry) {
    _entry = entry;
    notifyListeners();
  }

  void endExample() {
    if (!synthetic) return;
    _entry = EntryPoint.fresh;
    notifyListeners();
  }
}

class SessionScope extends InheritedNotifier<AppSession> {
  const SessionScope({
    super.key,
    required AppSession session,
    required super.child,
  }) : super(notifier: session);

  static AppSession of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<SessionScope>();
    assert(scope != null, 'SessionScope missing above this context');
    return scope!.notifier!;
  }
}
