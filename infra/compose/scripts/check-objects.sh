#!/bin/sh
# 영역 간 객체 저장소 권한 확인(시험용). 임시 객체는 마지막에 관리 신원으로 지운다.
# 공개 영역 신원은 공개 버킷에만, 개인 영역 신원은 개인 버킷에만 쓸 수 있어야 한다.
set -eu
key="smoke/probe-$$"
fail=0

as() { # as <access> <secret> <aws args...>
  a="$1"; s="$2"; shift 2
  AWS_MAX_ATTEMPTS=2 AWS_ACCESS_KEY_ID="$a" AWS_SECRET_ACCESS_KEY="$s" aws --cli-connect-timeout 5 --cli-read-timeout 30 "$@"
}
expect_ok() { # expect_ok <label> <access> <secret> <aws args...>
  label="$1"; shift
  if as "$@" >/dev/null 2>&1; then echo "ok   허용: $label"; else echo "FAIL 허용되어야 함: $label"; fail=1; fi
}
# 거부는 접근 거부 응답일 때만 인정한다. 연결 실패 같은 다른 오류를 거부로 세지 않는다.
expect_denied() {
  label="$1"; shift
  if out="$(as "$@" 2>&1)"; then
    echo "FAIL 거부되어야 함: $label"; fail=1
  elif printf '%s' "$out" | grep -qE 'AccessDenied|Forbidden|\(403\)'; then
    echo "ok   거부: $label"
  else
    echo "FAIL 접근 거부가 아닌 오류: $label"; fail=1
  fi
}

PA="$S3_PUBLIC_ACCESS_KEY"; PS="$S3_PUBLIC_SECRET_KEY"
VA="$S3_PRIVATE_ACCESS_KEY"; VS="$S3_PRIVATE_SECRET_KEY"

for b in "$S3_PUBLIC_RAW_BUCKET" "$S3_PUBLIC_DERIVED_BUCKET"; do
  expect_ok     "공개 영역 신원이 $b 에 쓴다"   "$PA" "$PS" s3api put-object --bucket "$b" --key "$key" --body /etc/hostname
  expect_ok     "공개 영역 신원이 $b 를 읽는다" "$PA" "$PS" s3api get-object --bucket "$b" --key "$key" /dev/null
  expect_denied "개인 영역 신원이 $b 에 쓴다"   "$VA" "$VS" s3api put-object --bucket "$b" --key "$key-x" --body /etc/hostname
  expect_denied "개인 영역 신원이 $b 를 읽는다" "$VA" "$VS" s3api get-object --bucket "$b" --key "$key" /dev/null
done
b="$S3_PRIVATE_BUCKET"
expect_ok     "개인 영역 신원이 $b 에 쓴다"   "$VA" "$VS" s3api put-object --bucket "$b" --key "$key" --body /etc/hostname
expect_ok     "개인 영역 신원이 $b 를 읽는다" "$VA" "$VS" s3api get-object --bucket "$b" --key "$key" /dev/null
expect_denied "공개 영역 신원이 $b 에 쓴다"   "$PA" "$PS" s3api put-object --bucket "$b" --key "$key-x" --body /etc/hostname
expect_denied "공개 영역 신원이 $b 를 읽는다" "$PA" "$PS" s3api get-object --bucket "$b" --key "$key" /dev/null

# 버킷 목록은 신원이 접근할 수 있는 버킷만 돌려준다(거부가 아니라 필터링).
visible() { as "$1" "$2" s3api list-buckets --query 'Buckets[].Name' --output text 2>/dev/null | tr '\t' '\n' | sort | tr '\n' ' '; }
want_public="$(printf '%s\n%s\n' "$S3_PUBLIC_RAW_BUCKET" "$S3_PUBLIC_DERIVED_BUCKET" | sort | tr '\n' ' ')"
if [ "$(visible "$PA" "$PS")" = "$want_public" ]; then echo "ok   공개 영역 신원에게는 공개 버킷만 보인다"; else echo "FAIL 공개 영역 신원에게 보이는 버킷이 다르다"; fail=1; fi
if [ "$(visible "$VA" "$VS")" = "$S3_PRIVATE_BUCKET " ]; then echo "ok   개인 영역 신원에게는 개인 버킷만 보인다"; else echo "FAIL 개인 영역 신원에게 보이는 버킷이 다르다"; fail=1; fi
expect_denied "공개 영역 신원이 버킷을 만든다" "$PA" "$PS" s3api create-bucket --bucket "zz-denied-$$"
expect_denied "개인 영역 신원이 버킷을 만든다" "$VA" "$VS" s3api create-bucket --bucket "zz-denied-$$"

# 정리: 관리 신원으로 임시 객체를 지운다.
for b in "$S3_PUBLIC_RAW_BUCKET" "$S3_PUBLIC_DERIVED_BUCKET" "$S3_PRIVATE_BUCKET"; do
  as "$S3_ADMIN_ACCESS_KEY" "$S3_ADMIN_SECRET_KEY" s3api delete-object --bucket "$b" --key "$key" >/dev/null 2>&1 || true
  as "$S3_ADMIN_ACCESS_KEY" "$S3_ADMIN_SECRET_KEY" s3api delete-object --bucket "$b" --key "$key-x" >/dev/null 2>&1 || true
done
exit "$fail"
