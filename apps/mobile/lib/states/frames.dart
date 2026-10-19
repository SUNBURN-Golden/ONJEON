import 'dart:async';

import 'package:flutter/material.dart';
import 'package:onjeon_contracts/onjeon_contracts.dart';

import '../design/tokens.g.dart';
import 'screen_state.dart';

/// Seven frames, one per common screen state. A frame owns the state's rule and wording and
/// shows the screen's own content inside it. None of them computes or formats an amount: amount
/// text arrives already built (design spec section 11).

const Duration kSlowLoadAfter = Duration(seconds: 2);

class _Band extends StatelessWidget {
  const _Band({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: OnjeonSpace.lg,
        vertical: OnjeonSpace.md,
      ),
      decoration: BoxDecoration(
        color: OnjeonColors.segBg,
        borderRadius: BorderRadius.circular(OnjeonSpace.sm),
      ),
      child: Text(text, style: OnjeonText.rowSubtitle),
    );
  }
}

/// 로딩: skeleton blocks; after [slowAfter] a sentence says it is taking longer.
class LoadingFrame extends StatefulWidget {
  const LoadingFrame({super.key, this.slowAfter = kSlowLoadAfter});

  final Duration slowAfter;

  @override
  State<LoadingFrame> createState() => _LoadingFrameState();
}

class _LoadingFrameState extends State<LoadingFrame> {
  Timer? _timer;
  bool _slow = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer(widget.slowAfter, () {
      if (mounted) setState(() => _slow = true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget bar(double width, double height) => Container(
          width: width,
          height: height,
          decoration: BoxDecoration(
            color: OnjeonColors.track,
            borderRadius: BorderRadius.circular(OnjeonSpace.xs),
          ),
        );
    return Column(
      key: const Key('state-loading'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        bar(180, 28),
        const SizedBox(height: OnjeonSpace.lg),
        for (var i = 0; i < 3; i++) ...[
          Row(
            children: [
              Container(
                width: OnjeonDimension.rowIconDiameter,
                height: OnjeonDimension.rowIconDiameter,
                decoration: const BoxDecoration(
                  color: OnjeonColors.track,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: OnjeonSpace.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    bar(140, 16),
                    const SizedBox(height: OnjeonSpace.sm),
                    bar(220, 12),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: OnjeonSpace.xl),
        ],
        if (_slow)
          const Text(
            '불러오는 데 시간이 걸리고 있어요. 잠시만 기다려 주세요.',
            key: Key('loading-slow'),
            style: OnjeonText.caption,
          ),
      ],
    );
  }
}

String holdingsLine(PolicyHoldingsStatus status) {
  switch (status) {
    case PolicyHoldingsStatus.confirmed:
      return '확인한 가입내역이 있어요';
    case PolicyHoldingsStatus.pendingConfirmation:
      return '올린 가입내역을 아직 확인하지 않았어요. 계산에는 쓰지 않아요';
    case PolicyHoldingsStatus.noneDeclared:
      return '보험이 없다고 답하셨어요 (본인 답변 기준)';
    case PolicyHoldingsStatus.unknown:
      return '가입내역을 모른다고 답하셨어요. 없는 것으로 보지 않아요';
    case PolicyHoldingsStatus.skipped:
      return '가입내역을 아직 올리지 않았어요';
  }
}

/// 비어 있음: no holdings (skipped, none, unknown). Shows the holdings status and keeps the
/// screen usable through 가입내역 없이 보기.
class EmptyFrame extends StatelessWidget {
  const EmptyFrame({
    super.key,
    required this.holdings,
    required this.onBrowseWithoutHoldings,
    this.message,
  });

  final PolicyHoldingsStatus holdings;
  final VoidCallback? onBrowseWithoutHoldings;

  /// What this screen shows once the user browses without holdings.
  final String? message;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('state-empty'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Band(text: holdingsLine(holdings)),
        if (message != null) ...[
          const SizedBox(height: OnjeonSpace.lg),
          Text(message!, style: OnjeonText.subhead),
        ],
        const SizedBox(height: OnjeonSpace.xl),
        _PrimaryButton(
          label: '가입내역 없이 보기',
          onPressed: onBrowseWithoutHoldings,
        ),
      ],
    );
  }
}

/// 부분: shows what is known and a 확인 필요 n건 badge. Never renders a total.
class PartialFrame extends StatelessWidget {
  const PartialFrame({
    super.key,
    required this.unresolvedCount,
    required this.child,
  });

  final int unresolvedCount;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('state-partial'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          key: const Key('unresolved-badge'),
          padding: const EdgeInsets.symmetric(
            horizontal: OnjeonSpace.md,
            vertical: OnjeonSpace.xs,
          ),
          decoration: BoxDecoration(
            border: Border.all(color: OnjeonColors.statusAdd),
            borderRadius: BorderRadius.circular(OnjeonSpace.lg),
          ),
          child: Text(
            '확인 필요 $unresolvedCount건',
            style: OnjeonText.rowSubtitle.copyWith(
              color: OnjeonColors.statusAdd,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        const SizedBox(height: OnjeonSpace.sm),
        const Text('아는 부분만 보여 드려요.', style: OnjeonText.caption),
        const SizedBox(height: OnjeonSpace.lg),
        child,
      ],
    );
  }
}

/// 판단 불가: one question, optionally a range sentence. Takes no amount widget and uses
/// no large figure style.
class UndecidableFrame extends StatelessWidget {
  const UndecidableFrame({super.key, required this.question, this.rangeText});

  final String question;
  final String? rangeText;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('state-undecidable'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('아직 판단할 수 없어요', style: OnjeonText.rowTitle),
        const SizedBox(height: OnjeonSpace.sm),
        Text(question, key: const Key('undecidable-question'), style: OnjeonText.subhead),
        if (rangeText != null) ...[
          const SizedBox(height: OnjeonSpace.sm),
          Text(rangeText!, style: OnjeonText.rowSubtitle),
        ],
      ],
    );
  }
}

/// 오래됨: freshness band above the unchanged result.
class StaleFrame extends StatelessWidget {
  const StaleFrame({super.key, this.asOf, required this.child});

  /// Release date as text from the server (`data_as_of`).
  final String? asOf;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('state-stale'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Band(
          text: asOf == null
              ? '최신 정보가 아닐 수 있어요'
              : '최신 정보가 아닐 수 있어요 · 기준일 $asOf',
        ),
        const SizedBox(height: OnjeonSpace.lg),
        child,
      ],
    );
  }
}

/// 오류: last successful result, the fact that refreshing failed, and a retry.
class ErrorFrame extends StatelessWidget {
  const ErrorFrame({super.key, required this.onRetry, this.lastResult});

  final VoidCallback? onRetry;
  final Widget? lastResult;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('state-error'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _Band(text: '새로 불러오지 못했어요'),
        if (lastResult != null) ...[
          const SizedBox(height: OnjeonSpace.sm),
          const Text('마지막으로 확인한 결과예요', style: OnjeonText.caption),
          const SizedBox(height: OnjeonSpace.lg),
          lastResult!,
        ],
        const SizedBox(height: OnjeonSpace.xl),
        _PrimaryButton(label: '다시 시도', onPressed: onRetry),
      ],
    );
  }
}

/// 변경됨: before and after text and why. Both texts are server-built lines.
class ChangedFrame extends StatelessWidget {
  const ChangedFrame({
    super.key,
    required this.cause,
    required this.before,
    required this.after,
  });

  final ChangeCause cause;
  final String before;
  final String after;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('state-changed'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('새 데이터로 결과가 바뀌었어요', style: OnjeonText.rowTitle),
        const SizedBox(height: OnjeonSpace.xs),
        Text(cause.label, key: const Key('change-cause'), style: OnjeonText.caption),
        const SizedBox(height: OnjeonSpace.lg),
        const Text('이전', style: OnjeonText.label),
        Text(before, style: OnjeonText.rowSubtitle),
        const SizedBox(height: OnjeonSpace.md),
        const Text('이후', style: OnjeonText.label),
        Text(after, style: OnjeonText.rowSubtitle),
      ],
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({required this.label, required this.onPressed});

  final String label;

  /// Null disables the button instead of leaving a tap that does nothing.
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: OnjeonDimension.buttonHeight,
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: OnjeonColors.accent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(OnjeonDimension.buttonRadius),
          ),
        ),
        child: Text(label, style: OnjeonText.button),
      ),
    );
  }
}

/// Everything a frame may need. A screen fills the fields of its current state only.
class FrameArgs {
  const FrameArgs({
    this.holdings = PolicyHoldingsStatus.skipped,
    this.onBrowseWithoutHoldings,
    this.emptyMessage,
    this.unresolvedCount = 0,
    this.question = '',
    this.rangeText,
    this.asOf,
    this.onRetry,
    this.cause = ChangeCause.sourceChanged,
    this.before = '',
    this.after = '',
  });

  final PolicyHoldingsStatus holdings;
  final VoidCallback? onBrowseWithoutHoldings;
  final String? emptyMessage;
  final int unresolvedCount;
  final String question;
  final String? rangeText;
  final String? asOf;
  final VoidCallback? onRetry;
  final ChangeCause cause;
  final String before;
  final String after;
}

/// Picks the frame for [state]. [content] is the screen's own widget (last or partial result);
/// states without content (loading, empty, undecidable, changed) ignore it.
class ScreenStateFrame extends StatelessWidget {
  const ScreenStateFrame({
    super.key,
    required this.state,
    this.content,
    this.args = const FrameArgs(),
  });

  final ScreenState state;
  final Widget? content;
  final FrameArgs args;

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case ScreenState.loading:
        return const LoadingFrame();
      case ScreenState.empty:
        return EmptyFrame(
          holdings: args.holdings,
          message: args.emptyMessage,
          onBrowseWithoutHoldings: args.onBrowseWithoutHoldings,
        );
      case ScreenState.partial:
        return PartialFrame(
          unresolvedCount: args.unresolvedCount,
          child: content ?? const SizedBox.shrink(),
        );
      case ScreenState.undecidable:
        return UndecidableFrame(question: args.question, rangeText: args.rangeText);
      case ScreenState.stale:
        return StaleFrame(asOf: args.asOf, child: content ?? const SizedBox.shrink());
      case ScreenState.error:
        return ErrorFrame(onRetry: args.onRetry, lastResult: content);
      case ScreenState.changed:
        return ChangedFrame(cause: args.cause, before: args.before, after: args.after);
    }
  }
}
