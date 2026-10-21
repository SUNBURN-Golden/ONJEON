import 'package:flutter/material.dart';

/// Paths the app registers. Skeleton (feature-flagged) surfaces never appear here
/// (`packages/schemas/feature_flags.json`); `test/skeleton_unexposed_test.dart` enforces it.
abstract final class AppPaths {
  static const entry = '/entry';
  static const home = '/home';
  static const whatIf = '/what-if';
  static const myDesign = '/my-design';
  static const me = '/me';
  static const evidencePattern = '/evidence/:ref';

  static String evidence(String ref) => '/evidence/${Uri.encodeComponent(ref)}';
}

/// A bottom-tab destination (Part 3 section 44.1: 홈, 만약에, 내 설계, 내 정보).
class TabSpec {
  const TabSpec({
    required this.label,
    required this.path,
    required this.icon,
    required this.question,
  });

  final String label;
  final String path;
  final IconData icon;

  /// The screen's core question (section 44.1).
  final String question;
}

const List<TabSpec> appTabs = [
  TabSpec(
    label: '홈',
    path: AppPaths.home,
    icon: Icons.home_outlined,
    question: '내가 가진 보장과 확인할 항목은?',
  ),
  TabSpec(
    label: '만약에',
    path: AppPaths.whatIf,
    icon: Icons.help_outline,
    question: '어떤 상황을 볼까요?',
  ),
  TabSpec(
    label: '내 설계',
    path: AppPaths.myDesign,
    icon: Icons.tune,
    question: '살펴볼 담보와 확인된 조건은?',
  ),
  TabSpec(
    label: '내 정보',
    path: AppPaths.me,
    icon: Icons.person_outline,
    question: '내 데이터는 어디에 어떻게 쓰이나요?',
  ),
];
