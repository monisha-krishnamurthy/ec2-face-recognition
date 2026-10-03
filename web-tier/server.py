from flask import Flask, request
import boto3, json, os, time, threading
from uuid import uuid4

app = Flask(__name__)

INPUT_BUCKET = "1233351056-in-bucket"
REQUEST_SQS = "1233351056-req-queue"
RESPONSE_SQS = "1233351056-resp-queue"
REGION = "us-east-1"

MAX_WAIT_SECONDS = 120
POLL_SLEEP = 0.5
CONSUMER_BATCH = 10
CONSUMER_WAIT = 20
VISIBILITY_TIMEOUT = 60

sqs = boto3.client("sqs", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

REQ_QUEUE_URL = sqs.get_queue_url(QueueName=REQUEST_SQS)["QueueUrl"]
RESP_QUEUE_URL = sqs.get_queue_url(QueueName=RESPONSE_SQS)["QueueUrl"]

results_store = {}
results_lock = threading.Lock()

def response_consumer():
    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=RESP_QUEUE_URL,
                MaxNumberOfMessages=CONSUMER_BATCH,
                WaitTimeSeconds=CONSUMER_WAIT,
                VisibilityTimeout=VISIBILITY_TIMEOUT,
                MessageAttributeNames=['All']
            )
            messages = resp.get("Messages", [])
            if not messages:
                continue

            for m in messages:
                try:
                    body = json.loads(m.get("Body", "{}"))
                except Exception:
                    body = {}

                request_id = body.get("request_id")
                filename = body.get("filename")
                key = request_id or filename
                if key:
                    with results_lock:
                        results_store[key] = {
                            "body": body,
                            "received_at": time.time()
                        }

                try:
                    sqs.delete_message(QueueUrl=RESP_QUEUE_URL, ReceiptHandle=m['ReceiptHandle'])
                except Exception:
                    pass

        except Exception:
            time.sleep(1)
            continue

def results_cleanup():
    TTL = 600
    while True:
        now = time.time()
        with results_lock:
            keys_to_delete = [k for k, v in results_store.items() if now - v["received_at"] > TTL]
            for k in keys_to_delete:
                del results_store[k]
        time.sleep(60)

consumer_thread = threading.Thread(target=response_consumer, daemon=True)
consumer_thread.start()

cleanup_thread = threading.Thread(target=results_cleanup, daemon=True)
cleanup_thread.start()

@app.route("/", methods=["POST"])
def upload():
    if "inputFile" not in request.files:
        return "No file uploaded", 400

    f = request.files["inputFile"]
    filename = os.path.basename(f.filename)
    f.stream.seek(0)
    try:
        s3.upload_fileobj(f.stream, INPUT_BUCKET, filename, ExtraArgs={"ContentType": f.content_type or "image/jpeg"})
    except Exception as e:
        return f"s3 upload failed: {e}", 500

    request_id = uuid4().hex
    msg = {"request_id": request_id, "filename": filename}
    try:
        sqs.send_message(QueueUrl=REQ_QUEUE_URL, MessageBody=json.dumps(msg))
    except Exception as e:
        return f"sqs send failed: {e}", 500

    start = time.time()
    while time.time() - start < MAX_WAIT_SECONDS:
        with results_lock:
            entry = results_store.get(request_id)
            if not entry:
                entry = results_store.get(filename)
                if not entry:
                    entry = results_store.get(os.path.splitext(filename)[0])
            if entry:
                body = entry["body"]
                try:
                    del results_store[request_id]
                except KeyError:
                    pass
                try:
                    del results_store[filename]
                except KeyError:
                    pass
                result_name = body.get("result_name", "")
                return f"{os.path.splitext(filename)[0]}:{result_name}", 200
        time.sleep(POLL_SLEEP)

    return "Timeout waiting for result", 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)