#!/bin/sh
# 버킷 생성(멱등). amazon/aws-cli 이미지 안에서 관리 신원으로 실행된다. 비밀키는 환경 변수로만 받는다.
set -eu
export AWS_MAX_ATTEMPTS=2 AWS_ACCESS_KEY_ID="$S3_ADMIN_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$S3_ADMIN_SECRET_KEY"

# 게이트웨이가 신원 파일을 읽고 응답할 때까지 기다린다.
i=0
until aws --cli-connect-timeout 5 --cli-read-timeout 30 s3api list-buckets >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -le 60 ] || { echo "s3-init: object store did not become ready" >&2; exit 1; }
  sleep 2
done

for bucket in "$S3_PUBLIC_RAW_BUCKET" "$S3_PUBLIC_DERIVED_BUCKET" "$S3_PRIVATE_BUCKET"; do
  if aws --cli-connect-timeout 5 --cli-read-timeout 30 s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
    echo "s3-init: $bucket exists"
  else
    aws --cli-connect-timeout 5 --cli-read-timeout 30 s3api create-bucket --bucket "$bucket" >/dev/null
    echo "s3-init: $bucket created"
  fi
done
