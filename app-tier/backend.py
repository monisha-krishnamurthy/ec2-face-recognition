import json
import time
import os
import uuid

INPUT_BUCKET = "1233351056-in-bucket"
OUTPUT_BUCKET = "1233351056-out-bucket"
REQUEST_SQS = "1233351056-req-queue"
RESPONSE_SQS = "1233351056-resp-queue"
REGION = "us-east-1"
POLL_WAIT = 20

def process_message(msg, *, s3, sqs, request_queue_url, response_queue_url, recognize):
    """Process one request; acknowledge only after storing and sending the result."""
    body = json.loads(msg["Body"])
    filename = body["filename"]
    request_id = body.get("request_id")

    local_path = f"/tmp/{os.path.basename(filename)}"
    s3.download_file(INPUT_BUCKET, filename, local_path)

    result_name = recognize(local_path)[0]

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
        QueueUrl=response_queue_url,
        MessageBody=json.dumps(response_payload)
    )

    sqs.delete_message(
        QueueUrl=request_queue_url,
        ReceiptHandle=msg["ReceiptHandle"]
    )

def main():
    import boto3
    from face_recognition import face_match

    s3 = boto3.client("s3", region_name=REGION)
    sqs = boto3.client("sqs", region_name=REGION)
    request_queue_url = sqs.get_queue_url(QueueName=REQUEST_SQS)["QueueUrl"]
    response_queue_url = sqs.get_queue_url(QueueName=RESPONSE_SQS)["QueueUrl"]
    while True:
        resp = sqs.receive_message(
            QueueUrl=request_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=POLL_WAIT,
            VisibilityTimeout=60,
        )
        messages = resp.get("Messages", [])
        if not messages:
            time.sleep(2)
            continue
        for msg in messages:
            process_message(
                msg, s3=s3, sqs=sqs,
                request_queue_url=request_queue_url,
                response_queue_url=response_queue_url,
                recognize=face_match,
            )


if __name__ == "__main__":
    main()
