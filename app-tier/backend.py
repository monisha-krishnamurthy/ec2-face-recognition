import json
import time
import boto3
import os
import uuid

INPUT_BUCKET = "1233351056-in-bucket"
OUTPUT_BUCKET = "1233351056-out-bucket"
REQUEST_SQS = "1233351056-req-queue"
RESPONSE_SQS = "1233351056-resp-queue"
REGION = "us-east-1"
POLL_WAIT = 20

s3 = boto3.client("s3", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)

REQ_QUEUE_URL = sqs.get_queue_url(QueueName=REQUEST_SQS)["QueueUrl"]
RESP_QUEUE_URL = sqs.get_queue_url(QueueName=RESPONSE_SQS)["QueueUrl"]

from face_recognition import face_match

def process_message(msg):
    body = json.loads(msg["Body"])
    filename = body["filename"]
    request_id = body.get("request_id")

    local_path = f"/tmp/{os.path.basename(filename)}"
    s3.download_file(INPUT_BUCKET, filename, local_path)

    result_name = face_match(local_path)[0]

    s3.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=f"{uuid.uuid4()}",
        Body=result_name.encode("utf-8")
    )

    response_payload = {
        "filename": filename,
        "request_id": request_id,
        "result_name": result_name,
        "status": "SUCCESS"
    }

    sqs.send_message(
        QueueUrl=RESP_QUEUE_URL,
        MessageBody=json.dumps(response_payload)
    )

    sqs.delete_message(
        QueueUrl=REQ_QUEUE_URL,
        ReceiptHandle=msg["ReceiptHandle"]
    )

while True:
    resp = sqs.receive_message(
        QueueUrl=REQ_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=POLL_WAIT,
        VisibilityTimeout=60
    )
    messages = resp.get("Messages", [])
    if not messages:
        time.sleep(2)
        continue
    for msg in messages:
        process_message(msg)