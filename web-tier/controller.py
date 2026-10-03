#!/usr/bin/env python3
import boto3, time, re

AWS_REGION = "us-east-1"
REQUEST_SQS_NAME = "1233351056-req-queue"
NAME_PREFIX = "app-tier-instance-"
WEB_TIER_NAME = "web-instance"
MIN_INSTANCES = 0
MAX_INSTANCES = 15
SCALE_UP_THRESHOLD = 5
SCALE_DOWN_THRESHOLD = 1
STABILITY_PERIOD = 10
POLL_INTERVAL = 2
DRY_RUN = False

boto3.setup_default_session(region_name=AWS_REGION)
ec2 = boto3.client("ec2")
sqs = boto3.client("sqs")

def qurl(name):
    return sqs.get_queue_url(QueueName=name)["QueueUrl"]

def queue_counts(url):
    a = sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
    )["Attributes"]
    visible = int(a.get("ApproximateNumberOfMessages", "0"))
    inflight = int(a.get("ApproximateNumberOfMessagesNotVisible", "0"))
    return visible, inflight

def pool_instances_by_name(prefix):
    resp = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}]
    )
    out = []
    for r in resp.get("Reservations", []):
        for i in r.get("Instances", []):
            name = ""
            for t in i.get("Tags", []):
                if t.get("Key") == "Name":
                    name = t.get("Value", "")
                    break
            if name == WEB_TIER_NAME:
                continue
            if name.startswith(prefix):
                m = re.search(rf"{re.escape(prefix)}(\d+)$", name)
                idx = int(m.group(1)) if m else 0
                out.append((name, i["InstanceId"], i["State"]["Name"], idx))
    out.sort(key=lambda x: x[3])
    return out

def start(ids):
    if not ids or DRY_RUN:
        return
    print(f"Starting {len(ids)} instances...")
    ec2.start_instances(InstanceIds=ids)

def stop(ids):
    if not ids or DRY_RUN:
        return
    print(f"Stopping {len(ids)} instances...")
    ec2.stop_instances(InstanceIds=ids)

def reconcile():
    url = qurl(REQUEST_SQS_NAME)
    stable_since = time.time()
    last_total = 0
    while True:
        try:
            visible, inflight = queue_counts(url)
            total = visible + inflight
            pool = pool_instances_by_name(NAME_PREFIX)
            running = [i for n,i,s,idx in pool if s == "running"]
            stopped = [i for n,i,s,idx in pool if s in ("stopped","stopping")]
            if abs(total - last_total) < 2:
                if time.time() - stable_since >= STABILITY_PERIOD:
                    if visible >= SCALE_UP_THRESHOLD and len(running) < MAX_INSTANCES:
                        need = min(MAX_INSTANCES - len(running), visible)
                        start(stopped[:need])
                    elif visible <= SCALE_DOWN_THRESHOLD and inflight == 0 and len(running) > MIN_INSTANCES:
                        stop(running)
                        stable_since = time.time()
            else:
                stable_since = time.time()
            last_total = total
        except Exception as e:
            print(f"Controller error: {e}")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    reconcile()