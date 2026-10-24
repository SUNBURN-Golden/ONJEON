// Amount-arithmetic lint (T-MB-01): screen code never adds, subtracts, scales or rounds a
// krw field. Amounts are computed by the rules engine and arrive as built text plus a
// declared source (design spec section 11).
//
//   dart run tool/krw_lint.dart [dir ...]     # default: lib
//
// Exit 0 clean, 1 findings, 2 usage. This is a textual check, not data-flow analysis:
//  * it reads identifiers whose name contains "krw" (any case), such as insuredAmountKrw or
//    amounts[0].krw, and one level of local aliases (final v = x.krw;);
//  * an arithmetic operator right next to such an operand, a rounding/conversion call on it
//    (.abs .round .floor .ceil .truncate .clamp .remainder .toDouble), or a fold/reduce/sum
//    in the same statement is a finding;
//  * comparison, equality and passing the value through are allowed;
//  * an amount renamed to something without "krw" and then used in arithmetic is not seen.
//    Review catches that; the generated types keep the krw suffix on purpose.
import 'dart:io';

class KrwFinding {
  const KrwFinding(this.path, this.line, this.message);

  final String path;
  final int line;
  final String message;

  @override
  String toString() => '$path:$line: KRW-ARITH $message';
}

final RegExp _ident = RegExp(r'[A-Za-z_$][A-Za-z0-9_$]*');
const String _opChars = '+-*/%';
const Set<String> _convert = {
  'abs', 'round', 'floor', 'ceil', 'truncate', 'clamp', 'remainder', 'toDouble', //
};
final RegExp _aggregate = RegExp(r'\.(?:fold|reduce|sum)\b|\bsum\s*\(');

bool _isKrwName(String s) => s.toLowerCase().contains('krw');

/// Drops comments and string text but keeps `$x` and `${...}` interpolations, which may
/// contain arithmetic. Line breaks stay, so line numbers survive.
String stripNonCode(String src) {
  final out = StringBuffer();
  var i = 0;
  final n = src.length;
  String at(int k) => k < n ? src[k] : '';
  while (i < n) {
    final c = src[i];
    if (c == '/' && at(i + 1) == '/') {
      while (i < n && src[i] != '\n') {
        i++;
      }
    } else if (c == '/' && at(i + 1) == '*') {
      i += 2;
      var depth = 1;
      while (i < n && depth > 0) {
        if (src[i] == '/' && at(i + 1) == '*') {
          depth++;
          i += 2;
        } else if (src[i] == '*' && at(i + 1) == '/') {
          depth--;
          i += 2;
        } else {
          if (src[i] == '\n') out.write('\n');
          i++;
        }
      }
    } else if (c == "'" || c == '"') {
      final raw = i > 0 && src[i - 1] == 'r';
      final triple = at(i + 1) == c && at(i + 2) == c;
      i += triple ? 3 : 1;
      out.write(' ');
      while (i < n) {
        final d = src[i];
        if (!raw && d == r'\') {
          i += 2;
        } else if (d == c && (!triple || (at(i + 1) == c && at(i + 2) == c))) {
          i += triple ? 3 : 1;
          break;
        } else if (!raw && d == r'$' && at(i + 1) == '{') {
          var depth = 1;
          out.write(' ');
          i += 2;
          final start = i;
          while (i < n && depth > 0) {
            if (src[i] == '{') depth++;
            if (src[i] == '}') depth--;
            i++;
          }
          out.write(stripNonCode(src.substring(start, i - 1)));
          out.write(' ');
        } else if (!raw && d == r'$' && _ident.matchAsPrefix(src, i + 1) != null) {
          final m = _ident.matchAsPrefix(src, i + 1)!;
          out.write(' ${m.group(0)} ');
          i = m.end;
        } else {
          if (d == '\n') out.write('\n');
          i++;
        }
      }
    } else {
      out.write(c);
      i++;
    }
  }
  return out.toString();
}

/// Index just past the operand chain that starts at [start] (an identifier):
/// `a.b?.c[0].d(x)!` and so on.
int _chainEnd(String s, int start) {
  var i = _ident.matchAsPrefix(s, start)!.end;
  while (i < s.length) {
    if (s[i] == '!' && !(i + 1 < s.length && s[i + 1] == '=')) {
      i++;
    } else if (s[i] == '[' || s[i] == '(') {
      i = _matchClose(s, i) + 1;
    } else if (s[i] == '.' || (s[i] == '?' && i + 1 < s.length && s[i + 1] == '.')) {
      final j = s[i] == '?' ? i + 2 : i + 1;
      final m = _ident.matchAsPrefix(s, j);
      if (m == null) break;
      i = m.end;
    } else {
      break;
    }
  }
  return i;
}

int _matchClose(String s, int open) {
  const pairs = {'[': ']', '(': ')'};
  final o = s[open];
  final c = pairs[o]!;
  var depth = 0;
  for (var i = open; i < s.length; i++) {
    if (s[i] == o) depth++;
    if (s[i] == c && --depth == 0) return i;
  }
  return s.length - 1;
}

/// Start of the operand chain that contains the identifier at [start].
int _chainStart(String s, int start) {
  var i = start;
  while (true) {
    var j = i - 1;
    while (j >= 0 && s[j] == ' ') {
      j--;
    }
    final dot = j >= 0 && s[j] == '.' && !(j > 0 && s[j - 1] == '.');
    if (!dot) return i;
    j--;
    if (j >= 0 && s[j] == '?') j--;
    if (j >= 0 && (s[j] == ')' || s[j] == ']')) {
      final close = s[j];
      final open = close == ')' ? '(' : '[';
      var depth = 0;
      while (j >= 0) {
        if (s[j] == close) depth++;
        if (s[j] == open && --depth == 0) break;
        j--;
      }
      j--;
    }
    if (j >= 0 && s[j] == '!') j--;
    var k = j;
    while (k >= 0 && RegExp(r'[A-Za-z0-9_$]').hasMatch(s[k])) {
      k--;
    }
    if (k == j) return i;
    i = k + 1;
  }
}

bool _isWs(String c) => c == ' ' || c == '\n' || c == '\t' || c == '\r';

int _line(String s, int index) => '\n'.allMatches(s.substring(0, index)).length + 1;

List<KrwFinding> lintSource(String path, String source) {
  final code = stripNonCode(source);
  final tainted = <String>{};
  final alias = RegExp(
    r'\b(?:final|var|const|int|num|double)\s+(?:int\s+|num\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*([^;=][^;]*);',
  );
  for (var pass = 0; pass < 2; pass++) {
    for (final m in alias.allMatches(code)) {
      final rhs = m.group(2)!.trim();
      final first = _ident.matchAsPrefix(rhs);
      if (first == null) continue;
      final chain = rhs.substring(0, _chainEnd(rhs, 0));
      final isChainOnly = chain.length == rhs.length;
      final hasKrw = _ident.allMatches(chain).any((x) => _isKrwName(x.group(0)!) || tainted.contains(x.group(0)));
      if (isChainOnly && hasKrw) tainted.add(m.group(1)!);
    }
  }

  final findings = <KrwFinding>[];
  final seen = <int>{};
  void add(int index, String msg) {
    final line = _line(code, index);
    if (seen.add(line * 1000 + msg.length)) findings.add(KrwFinding(path, line, msg));
  }

  for (final m in _ident.allMatches(code)) {
    final name = m.group(0)!;
    if (!_isKrwName(name) && !tainted.contains(name)) continue;
    // The match must be the last link of its chain for the operand to be this value.
    final end = _chainEnd(code, m.start);
    final start = _chainStart(code, m.start);
    var r = end;
    while (r < code.length && _isWs(code[r])) {
      r++;
    }
    var l = start - 1;
    while (l >= 0 && _isWs(code[l])) {
      l--;
    }
    final next = r < code.length ? code[r] : '';
    final next2 = r + 1 < code.length ? code[r + 1] : '';
    if (next.isNotEmpty && _opChars.contains(next)) {
      add(m.start, 'arithmetic on "$name": operator "$next$next2" follows it');
    } else if (next == '~' && next2 == '/') {
      add(m.start, 'arithmetic on "$name": operator "~/" follows it');
    } else if (l >= 0 && _opChars.contains(code[l])) {
      add(m.start, 'arithmetic on "$name": operator "${code[l]}" precedes it');
    } else if (l > 0 && code[l] == '=' && _opChars.contains(code[l - 1])) {
      add(m.start, 'arithmetic on "$name": compound assignment "${code[l - 1]}=" precedes it');
    }
    // Conversion or rounding called on the chain: x.krw.abs(), x.krw.round()
    for (final c in RegExp(r'\.([A-Za-z]+)\s*\(').allMatches(code.substring(start, end))) {
      if (_convert.contains(c.group(1))) {
        add(m.start, 'amount "$name" passed through .${c.group(1)}()');
      }
    }
    // Aggregation in the same statement.
    var s = m.start;
    while (s > 0 && code[s - 1] != ';' && code[s - 1] != '{' && code[s - 1] != '}') {
      s--;
    }
    var e = m.end;
    while (e < code.length && code[e] != ';') {
      e++;
    }
    if (_aggregate.hasMatch(code.substring(s, e))) {
      add(m.start, 'amount "$name" is aggregated (fold/reduce/sum) in one statement');
    }
  }
  findings.sort((a, b) => a.line.compareTo(b.line));
  return findings;
}

List<KrwFinding> lintTree(Directory dir, {String? relativeTo}) {
  final out = <KrwFinding>[];
  final files = dir.listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart')).toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  for (final f in files) {
    if (f.path.endsWith('.g.dart')) continue; // generated token file has no amounts
    final shown = relativeTo != null && f.path.startsWith(relativeTo) ? f.path.substring(relativeTo.length) : f.path;
    out.addAll(lintSource(shown, f.readAsStringSync()));
  }
  return out;
}

void main(List<String> args) {
  final dirs = args.isEmpty ? ['lib'] : args;
  var findings = 0;
  for (final d in dirs) {
    final dir = Directory(d);
    if (!dir.existsSync()) {
      stderr.writeln('no such directory: $d');
      exit(2);
    }
    for (final f in lintTree(dir)) {
      stdout.writeln(f);
      findings++;
    }
  }
  if (findings == 0) stdout.writeln('krw_lint: clean (${dirs.join(', ')})');
  exit(findings == 0 ? 0 : 1);
}
