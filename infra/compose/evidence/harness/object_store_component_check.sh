#!/bin/bash
# 실제 SeaweedFS 4.48 바이너리에 저장소의 신원 파일 생성기·init-objects.sh·check-objects.sh를 실행한다(Docker 대체 검증).
set -u
C=/workspace/onjeon-run/wt/T-OP-01/infra/compose
rm -rf /tmp/weedstate /tmp/weeddata; mkdir -p /tmp/weeddata
echo "weed: $(/tmp/weed/weed version | head -1 | sed -E 's/ [0-9a-f]{40}//')"
ONJEON_COMPOSE_STATE_DIR=/tmp/weedstate bash -c ". $C/lib.sh; ensure_env; render_s3_config; echo 'identities rendered (mode '\$(stat -c %a \$S3_CONFIG_FILE)')'"
(/tmp/weed/weed server -dir=/tmp/weeddata -ip.bind=0.0.0.0 -s3 -s3.port=18333 -s3.config=/tmp/weedstate/.generated/s3.json -master.volumeSizeLimitMB=128 -volume.max=0 -master.port=19333 -volume.port=18080 -filer.port=18888 > /tmp/weed.log 2>&1 &)
for i in $(seq 30); do wget -S -O /dev/null http://127.0.0.1:18333/ 2>&1 | grep -q 'HTTP/' && break; sleep 1; done
echo "health probe (compose healthcheck command): $(wget -S -O /dev/null http://127.0.0.1:18333/ 2>&1 | grep -m1 'HTTP/' | tr -s ' ')"
set -a; . /tmp/weedstate/.env; set +a
export PATH=/tmp/awsbin:$PATH AWS_ENDPOINT_URL=http://127.0.0.1:18333 AWS_DEFAULT_REGION=us-east-1 AWS_EC2_METADATA_DISABLED=true AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
echo "--- init-objects.sh (1st)"; sh $C/scripts/init-objects.sh; echo "exit $?"
echo "--- init-objects.sh (2nd, idempotent)"; sh $C/scripts/init-objects.sh; echo "exit $?"
echo "--- check-objects.sh"; sh $C/scripts/check-objects.sh; rc=$?; echo "exit $rc"
echo "--- check-objects.sh against a dead endpoint (every check must FAIL, none may pass as 'denied')"
AWS_ENDPOINT_URL=http://127.0.0.1:1 sh $C/scripts/check-objects.sh | awk '/^FAIL/{f++} /^ok/{o++} END{print "FAIL lines:", f+0, " ok lines:", o+0}'
pkill -x weed; sleep 3; pkill -9 -x weed; rm -rf /tmp/weeddata /tmp/weedstate
exit $rc
