# packages/design-tokens

Single source of the app's visual tokens: `tokens.json`. Values are the measured numbers of the selected reference screen (`docs/design/화면_조작_설계서.md` section 3) and the spacing scale of `docs/design/UX_UI_REFERENCE.md` section 1. They carry the spec's tolerance and are not final until P0 (spec section 13); no font family is named because it is undecided.

```text
python3 -I packages/design-tokens/gen_dart.py           # writes apps/mobile/lib/design/tokens.g.dart
python3 -I packages/design-tokens/gen_dart.py --check   # fails when the committed file is stale
python3 -I -m unittest discover -s packages/design-tokens/tests
```

To change a value, edit `tokens.json` and regenerate. Do not edit the generated Dart file. The web app (T-WB tasks) will add its own generator against the same JSON.
