from datetime import datetime
import logging
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

from main import EventProcessor, parse_line, run_serial
from notifier import NotificationWorker, build_transports


class ParsingTests(unittest.TestCase):
    def test_protocol(self):
        for line, expected in [('BREACH\r\n', ('BREACH', None)), (' CLEAR ', ('CLEAR', None)),
                               ('ENV 12.5', ('ENV', 12.5)), ('ENV -2', ('ENV', -2.0)),
                               ('MISSED 3', ('MISSED', 3)),
                               ('READY FS=8000 sections=4', ('READY', 'FS=8000 sections=4'))]:
            with self.subTest(line=line):
                self.assertEqual(parse_line(line), expected)

    def test_invalid(self):
        for line in ['', 'BREACH extra', 'clear', 'ENV', 'ENV nan', 'ENV inf',
                     'ENV x', 'MISSED -1', 'MISSED 2.5', 'READY', 'READY FS=1', 'unknown']:
            with self.subTest(line=line):
                self.assertIsNone(parse_line(line))


class EventTests(unittest.TestCase):
    def setUp(self):
        self.notifier = Mock()
        self.processor = EventProcessor(self.notifier, lambda: datetime(2026, 10, 16, 13, 20))

    def test_duplicates_and_repeated_interruptions(self):
        for line in ['BREACH', 'BREACH', 'ENV 12', 'MISSED 1',
                     'READY FS=1000 sections=2', 'BREACH']:
            self.processor.process(line)
        self.notifier.submit.assert_called_once_with(
            'Critical Safety Event at 01:20 PM on 10/16/2026')
        self.processor.process('CLEAR')
        self.processor.process('BREACH')
        self.assertEqual(self.notifier.submit.call_count, 2)

    def test_clear_and_invalid_do_not_alert(self):
        for line in ['CLEAR', 'ENV bad', 'noise']:
            self.processor.process(line)
        self.notifier.submit.assert_not_called()

    def test_serial_fragmentation_and_reconnection(self):
        class SerialError(Exception):
            pass
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.read.side_effect = [b'BRE', b'ACH\r\nBREACH\n', SerialError('lost')]
        serial = types.SimpleNamespace(Serial=Mock(return_value=connection), SerialException=SerialError)
        with patch.dict(sys.modules, {'serial': serial}), patch('main.time.sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_serial(self.processor, '/dev/fake')
        serial.Serial.assert_called_once_with('/dev/fake', 115200, timeout=1)
        self.assertTrue(self.processor.active)
        self.processor.process('BREACH')
        self.notifier.submit.assert_called_once()


class WorkerTests(unittest.TestCase):
    def test_failure_is_logged_and_later_deliveries_continue(self):
        failing = Mock(side_effect=OSError('offline'))
        success = Mock()
        with self.assertLogs(level=logging.INFO) as logs:
            worker = NotificationWorker([('failed', failing), ('ok', success)])
            worker.submit('first')
            worker.submit('second')
            worker.close()
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(success.call_count, 2)
        self.assertEqual(failing.call_count, 2)
        self.assertTrue(any('Delivery failed' in line for line in logs.output))
        self.assertTrue(any('Delivery successful' in line for line in logs.output))

    def test_network_wait_does_not_block_event_processing(self):
        started, release = threading.Event(), threading.Event()
        def slow_send(message):
            started.set()
            release.wait(3)
        worker = NotificationWorker([('slow', slow_send)])
        try:
            processor = EventProcessor(worker)
            processor.process('BREACH')
            self.assertTrue(started.wait(1))
            processor.process('CLEAR')
            processor.process('BREACH')
            self.assertTrue(processor.active)
            self.assertEqual(worker.pending.qsize(), 1)
        finally:
            release.set()
            worker.close()

    def test_console_configuration(self):
        with patch.dict('os.environ', {'ALERT_CHANNELS': 'console'}, clear=True):
            channels = build_transports()
        with patch('builtins.print') as output:
            channels[0][1]('exact message')
        output.assert_called_once_with('exact message', flush=True)

    def test_configuration_errors(self):
        for settings in [{'ALERT_CHANNELS': 'invalid'}, {'ALERT_CHANNELS': 'smtp'},
                         {'ALERT_CHANNELS': 'ntfy', 'NTFY_URL': 'http://example.com/topic'}]:
            with self.subTest(settings=settings), patch.dict('os.environ', settings, clear=True):
                with self.assertRaises((ValueError, KeyError)):
                    build_transports()


class GmailTests(unittest.TestCase):
    def settings(self):
        # Synthetic test values only; no local .env or credentials are read.
        return {'SMTP_FROM': 'sender@example.test', 'SMTP_TO': 'recipient@example.test',
                'SMTP_USERNAME': 'sender@example.test', 'SMTP_PASSWORD': 'fake-app-password'}

    def test_gmail_defaults_use_ssl_and_one_send(self):
        with patch.dict('os.environ', self.settings(), clear=True), \
                patch('notifier.smtplib.SMTP_SSL') as ssl_client, \
                patch('notifier.smtplib.SMTP') as plain_client:
            client = ssl_client.return_value.__enter__.return_value
            client.send_message.return_value = {}
            transports = build_transports()
            self.assertEqual([name for name, _ in transports], ['smtp'])
            transports[0][1]('test event')
            self.assertEqual(ssl_client.call_args.args, ('smtp.gmail.com', 465))
            self.assertEqual(ssl_client.call_args.kwargs['timeout'], 10)
            self.assertTrue(ssl_client.call_args.kwargs['context'].check_hostname)
            plain_client.assert_not_called()
            client.starttls.assert_not_called()
            client.login.assert_called_once()
            client.send_message.assert_called_once()
            mail = client.send_message.call_args.args[0]
            self.assertEqual(mail['From'], 'sender@example.test')
            self.assertEqual(mail['To'], 'recipient@example.test')
            self.assertEqual(mail['Subject'], 'test event')

    def test_gmail_rejects_missing_password_and_wrong_security(self):
        for override in [{'SMTP_PASSWORD': ''}, {'SMTP_SECURITY': 'starttls'},
                         {'SMTP_PORT': '587'}]:
            with self.subTest(override=override), \
                    patch.dict('os.environ', self.settings() | override, clear=True):
                with self.assertRaises(ValueError):
                    build_transports()

    def test_one_email_cli_ignores_other_channels_and_serial(self):
        from main import main
        send = Mock()
        with patch('sys.argv', ['main.py', '--test-email']), \
                patch('main.build_transports', return_value=[('smtp', send)]) as build, \
                patch('main.run_serial') as serial_run, \
                patch('main.NotificationWorker') as worker, \
                patch('main.logging.basicConfig'), patch('main.logging.FileHandler'):
            main()
        build.assert_called_once_with('smtp')
        send.assert_called_once()
        serial_run.assert_not_called()
        worker.assert_not_called()

    def test_one_email_failure_exits_without_exposing_exception(self):
        from main import main
        send = Mock(side_effect=RuntimeError('sensitive-server-response'))
        with patch('sys.argv', ['main.py', '--test-email']), \
                patch('main.build_transports', return_value=[('smtp', send)]), \
                patch('main.logging.basicConfig'), patch('main.logging.FileHandler'), \
                self.assertLogs(level=logging.ERROR) as logs:
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 1)
        self.assertNotIn('sensitive-server-response', '\n'.join(logs.output))
        send.assert_called_once()


class ESP32IntegrationTests(unittest.TestCase):
    def test_csv_spectrum_and_help_never_trigger_or_clear_a_breach(self):
        sender = Mock()
        processor = EventProcessor(sender, lambda: datetime(2026, 10, 16, 13, 20))
        diagnostics = ['# 1200 ms: beam BROKEN', '# BREACH is only a help word',
                       '1200,500.0,12.5,500.0,12.5,8.0,16.0,1.0,2.0,3.0,2,1,10,4000,0',
                       '# SPECTRUM_BEGIN freq_hz,amp_mV_at_adc,amp_dB_re_1mV',
                       '500.0,12.500,21.94', '# SPECTRUM_END', '# 1500 ms: beam PRESENT']
        with self.assertNoLogs('main', level='WARNING'):
            for line in diagnostics:
                processor.process(line)
        sender.submit.assert_not_called()
        processor.process('BREACH')
        for line in diagnostics:
            processor.process(line)
        processor.process('BREACH')
        self.assertTrue(processor.active)
        self.assertEqual(sender.submit.call_count, 1)
        processor.process('CLEAR')
        processor.process('BREACH')
        self.assertEqual(sender.submit.call_count, 2)

    def test_keyboard_simulation_rearms_without_hardware(self):
        from main import simulate
        sender = Mock()
        processor = EventProcessor(sender)
        with patch('builtins.input', side_effect=['b','b','c','b','q']), \
                patch('builtins.print'):
            simulate(processor)
        self.assertEqual(sender.submit.call_count, 2)
