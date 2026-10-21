# apps/mobile: ONJEON consumer app skeleton (T-MB-01)

Flutter frame for the consumer app: four tabs, three entry points, the seven common screen states, design tokens, example-mode marking, and the static checks that keep the frame honest. **There are no feature screens or data yet.** Every tab says so on screen (`NotConnectedNotice`) instead of showing a made-up value. Real screens come from T-MB-02 (coverage detail, evidence), T-MB-03 and T-MB-04.

## What is here

| Part | Where | Source |
|---|---|---|
| Four tabs 홈 / 만약에 / 내 설계 / 내 정보, common 증거 보기 route | `lib/app/` (`routes.dart`, `router.dart`, `shell.dart`) | Part 3 section 44.1 |
| Three entry points 예시로 둘러보기 / 처음부터 준비하기 / 가입내역 PDF 올리기 | `lib/screens/entry_points.dart`, first-run `/entry`, top of 홈 until one is chosen | Part 3 section 43.4 |
| Example mode: banner `화면 예시 · 실제 견적 아님` plus `synthetic=true` on every screen while on | `SyntheticFrame` (MaterialApp builder, every route) in `lib/app/shell.dart`, `AppSession.synthetic` | design spec C1, section 9 |
| Seven state frames (loading, empty, partial, undecidable, stale, error, changed) and `ScreenStateFrame` | `lib/states/` | Part 3 section 44.2, design spec section 9 |
| Design tokens | `packages/design-tokens/tokens.json` to `lib/design/tokens.g.dart` | design spec section 3 |
| Amount-arithmetic lint | `tool/krw_lint.dart` (`dart run tool/krw_lint.dart`) | design spec section 11, Part 3 section 44.5 |

Tab state survives tab switches (`StatefulShellRoute`). `/entry` is the first-run location; every tab and `/evidence/:ref` also open by deep link with no choice made, so reading coverage and source text never needs a PDF, family history, consent or a consultation (R01).

## Rules the tests enforce

- **No HTTP outside the generated client.** `lib/` has no HTTP, socket, URL-launch or web-view code and `pubspec.yaml` has no such package (`test/no_http_outside_client_test.dart`). The generated Dart packages under `packages/schemas/codegen/generated` currently give types and an operation table but no transport, so the app makes no call at all yet. The only generated package imported is `onjeon_contracts` (the policy-holdings status enum).
- **Skeleton surfaces are not exposed.** Paths, flag ids and features come from `packages/schemas/feature_flags.json`; no registered route, tab or source string matches them, and deep links to them land on the not-found screen (`test/skeleton_unexposed_test.dart`). The same file runs the CI probe `probe_ui_routes` from `tools/ci/check_skeleton.py` on the real route table.
- **No amount arithmetic in screen code.** `tool/krw_lint.dart` rejects `+ - * / ~/ %`, compound assignment, `++`/`--`, negation, `.abs() .round() .floor() .ceil() .truncate() .clamp() .remainder() .toDouble()` and `fold`/`reduce`/`sum` on any identifier containing `krw`, and on one level of local aliases. It is textual and reads across line breaks. It does not see through parentheses around an operand. It does not follow an amount that is renamed to a name without `krw`; the generated types keep the suffix so that review can rely on it. `test/krw_lint_test.dart` plants 25 violations and 11 allowed uses and scans all of `lib/`.
- **No invented numbers.** `lib/` has no price, payout or sample amount. The only numbers in the UI are counts passed in (`확인 필요 n건`) and layout sizes from the tokens.
- **Tokens do not drift.** `python3 -I packages/design-tokens/gen_dart.py --check` and `test/design_tokens_test.dart`.

## Run

```text
cd apps/mobile && flutter pub get && flutter analyze && flutter test
dart run tool/krw_lint.dart
python3 -I packages/design-tokens/gen_dart.py --check
python3 -I -m unittest discover -s packages/design-tokens/tests
python3 -I tools/ci/check_deps.py && python3 -I tools/ci/check_leak.py && python3 -I tools/ci/check_skeleton.py
```

`flutter test` needs `python3` on the path for the skeleton probe test; a missing interpreter fails the test, it does not skip. Logs of the last run are in `evidence/`.

## Known limits and open items

- **Not wired in CI.** `.github/workflows/` is outside this task. `flutter analyze`, `flutter test` and the token check must be added to `ci.yml` by whoever owns it.
- **`infra/ci/deps.json` names the generated client packages `onjeon_contracts` and `onjeon_api_types`; the generated Dart API package is called `onjeon_api`.** `check_deps` therefore reports `IMP-CLIENT` for any import of `onjeon_api`. That file is outside this task's paths, so the app does not import `onjeon_api`. Whoever wires the first real call adds `onjeon_api` (or the name used then) to `client_rules.generated_client_packages`.
- **No transport yet.** The first API-backed screen (T-MB-02) needs an HTTP layer inside the generated client; the no-HTTP test then has to name that package as the one allowed place.
- **No platform folders** (`android/`, `ios/`, `web/`). Bundle ids, signing and the app store identity are a separate decision, so `flutter create` has not been run.
- **Font family is undecided** (design spec section 13); none is named and the platform UI font is used.
- **Token values are the spec's measurements** (position +-2dp, colour +-6) and become final in P0. The reference-image overlay check (design spec section 12.1) is not done: it needs the final tokens and real screens.
- **The seven frames exist; the all-screens x seven-states capture catalog does not.** It belongs with the real screens (WP40). Today `test/states_test.dart` renders each frame, its wording and its rule (2-second slow-load sentence, no total on partial, no large figure on undecidable, last result kept on error, cause shown on changed).
- **Screen-state names are an app-side axis,** not part of `vocabulary.json` (that file is outside this task). If the contract later defines them, generate them instead of keeping `ScreenState` and `ChangeCause`.
- **Entry point 3 only navigates to 내 정보.** The PDF import is T-MB-04; the holdings status stays "not uploaded yet" and nothing claims otherwise.
- **Example mode is a marking, not data.** `synthetic=true` is shown whenever the example entry was chosen; synthetic content itself arrives with the screens that read it, and must come from fixtures marked `origin=fixture`.
- This is a layout and wiring check by widget tests. It is not a usability result and says nothing about product accuracy.
