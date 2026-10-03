import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    'worker', Path(__file__).resolve().parents[1] / 'app-tier/backend.py'
)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.events = Mock()
        self.s3 = self.events.s3
        self.sqs = self.events.sqs
        self.recognize = self.events.recognize
        self.recognize.return_value = ('Paul', 0.5)
        self.msg = {'Body': json.dumps({'filename': 'photo.jpg', 'request_id': 'req-123'}),
                    'ReceiptHandle': 'receipt-456'}

    def process(self):
        worker.process_message(self.msg, s3=self.s3, sqs=self.sqs,
                               request_queue_url='request-url', response_queue_url='response-url',
                               recognize=self.recognize)

    def test_success_routes_and_acknowledges_in_order(self):
        self.process()
        self.s3.download_file.assert_called_once_with(worker.INPUT_BUCKET, 'photo.jpg', '/tmp/photo.jpg')
        self.recognize.assert_called_once_with('/tmp/photo.jpg')
        stored = self.s3.put_object.call_args.kwargs
        self.assertEqual(stored['Bucket'], worker.OUTPUT_BUCKET)
        self.assertEqual(stored['Body'], b'Paul')
        self.assertTrue(stored['Key'])
        sent = self.sqs.send_message.call_args.kwargs
        self.assertEqual(sent['QueueUrl'], 'response-url')
        self.assertEqual(json.loads(sent['MessageBody']), {
            'filename': 'photo.jpg', 'request_id': 'req-123', 'result_name': 'Paul', 'status': 'SUCCESS'})
        self.sqs.delete_message.assert_called_once_with(QueueUrl='request-url', ReceiptHandle='receipt-456')
        self.assertEqual([c[0] for c in self.events.mock_calls], [
            's3.download_file', 'recognize', 's3.put_object', 'sqs.send_message', 'sqs.delete_message'])

    def test_failures_do_not_acknowledge_request(self):
        for stage in ('download', 'recognition', 'storage', 'response'):
            with self.subTest(stage=stage):
                self.setUp()
                target = {'download': self.s3.download_file, 'recognition': self.recognize,
                          'storage': self.s3.put_object, 'response': self.sqs.send_message}[stage]
                target.side_effect = RuntimeError(stage)
                with self.assertRaisesRegex(RuntimeError, stage):
                    self.process()
                self.sqs.delete_message.assert_not_called()
                if stage != 'response':
                    self.sqs.send_message.assert_not_called()

    def test_invalid_message_does_not_touch_services(self):
        self.msg['Body'] = '{}'
        with self.assertRaises(KeyError):
            self.process()
        self.assertEqual(self.events.mock_calls, [])

    def test_import_does_not_load_aws_or_model(self):
        import builtins
        original = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name in ('boto3', 'face_recognition'):
                raise AssertionError('Import attempted to initialize runtime dependencies')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded):
            SPEC.loader.exec_module(importlib.util.module_from_spec(SPEC))


if __name__ == '__main__':
    unittest.main()
