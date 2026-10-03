# EC2 Face Recognition Service

A Python face-recognition workflow using a Flask web tier, Amazon S3, Amazon SQS, and EC2 inference workers. Developed for CSE 546 Cloud Computing, Project 1 Part II.

## How it works

1. The Flask endpoint accepts an image, stores it in S3, and sends a request to SQS.
2. An EC2 worker downloads the image and runs the externally supplied recognition model.
3. The worker stores the result in S3 and sends a response through a second SQS queue.
4. The web tier correlates the response with the request and returns the result.

A separate controller monitors queue depth and starts or stops pre-provisioned EC2 workers, with a configured maximum of 15 instances. It does not create instances or provision infrastructure.

## Source layout

- `web-tier/server.py` — HTTP uploads and response coordination.
- `web-tier/controller.py` — queue-based EC2 start/stop controller.
- `app-tier/backend.py` — image processing and result delivery.

## Deployment prerequisites

This repository contains application source from the course submission. It is not a self-contained deployment package.

- Install Flask and boto3 for the web tier; install the recognition model's dependencies on workers.
- Supply the course-provided `face_recognition` module exposing `face_match`, plus its model assets.
- Create input/output S3 buckets, request/response SQS queues, and an EC2 worker pool with the expected Name tags.
- Update region, bucket, queue, and instance-name constants in the source to match your environment.
- Configure AWS access through IAM roles or your local AWS credential provider; credentials are excluded from this repository.
- Arrange for workers to start `backend.py` at boot before using the scaling controller.

The controller has `DRY_RUN = False`; running it can start and stop matching EC2 instances.

## Scope and validation

The source was checked for Python syntax. End-to-end AWS behavior and performance have not been revalidated for this repository. The web tier uses in-memory response coordination, so horizontal web-tier scaling would require additional coordination.

Course-provided model assets, credentials, and assignment PDFs are not bundled.
