import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from change import AWSRoute53RecordSet, DEFAULT_TTL, SUPPORTED_RECORD_TYPES, SUPPORTED_ACTIONS


class TestGetEnv(unittest.TestCase):
    """Tests for environment variable retrieval and missing-var behaviour."""

    def setUp(self):
        self.rr = AWSRoute53RecordSet()

    @patch.dict(os.environ, {"MY_VAR": "hello"})
    def test_returns_value_when_present(self):
        self.assertEqual(self.rr._get_env("MY_VAR"), "hello")

    def test_raises_when_required_and_missing(self):
        with self.assertRaises(NameError):
            self.rr._get_env("DOES_NOT_EXIST", exit_on_missing=True)

    def test_returns_none_when_optional_and_missing(self):
        self.assertIsNone(self.rr._get_env("DOES_NOT_EXIST", exit_on_missing=False))

    @patch.dict(os.environ, {"EMPTY_VAR": ""})
    def test_empty_string_is_not_treated_as_missing(self):
        self.assertEqual(self.rr._get_env("EMPTY_VAR", exit_on_missing=True), "")


class TestValidateRecordType(unittest.TestCase):

    def setUp(self):
        self.rr = AWSRoute53RecordSet()

    def test_all_supported_types_pass(self):
        for rt in SUPPORTED_RECORD_TYPES:
            self.rr._validate_record_type(rt)

    def test_unsupported_type_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self.rr._validate_record_type("INVALID")
        self.assertIn("INVALID", str(ctx.exception))

    def test_lowercase_type_raises(self):
        with self.assertRaises(ValueError):
            self.rr._validate_record_type("a")


class TestValidateAction(unittest.TestCase):

    def setUp(self):
        self.rr = AWSRoute53RecordSet()

    def test_all_supported_actions_pass(self):
        for action in SUPPORTED_ACTIONS:
            self.rr._validate_action(action)

    def test_unsupported_action_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self.rr._validate_action("UPDATE")
        self.assertIn("UPDATE", str(ctx.exception))

    def test_lowercase_action_raises(self):
        with self.assertRaises(ValueError):
            self.rr._validate_action("create")


class TestValidateTTL(unittest.TestCase):

    def setUp(self):
        self.rr = AWSRoute53RecordSet()

    def test_valid_ttl(self):
        self.assertEqual(self.rr._validate_ttl("600"), 600)

    def test_zero_ttl(self):
        self.assertEqual(self.rr._validate_ttl("0"), 0)

    def test_max_ttl(self):
        self.assertEqual(self.rr._validate_ttl("2147483647"), 2147483647)

    def test_none_returns_default(self):
        self.assertEqual(self.rr._validate_ttl(None), DEFAULT_TTL)

    def test_empty_string_returns_default(self):
        self.assertEqual(self.rr._validate_ttl(""), DEFAULT_TTL)

    def test_negative_ttl_raises(self):
        with self.assertRaises(ValueError):
            self.rr._validate_ttl("-1")

    def test_overflow_ttl_raises(self):
        with self.assertRaises(ValueError):
            self.rr._validate_ttl("2147483648")

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            self.rr._validate_ttl("abc")


class TestSetOutput(unittest.TestCase):

    def setUp(self):
        self.rr = AWSRoute53RecordSet()

    def test_writes_to_github_output_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_path}):
                self.rr._set_output("change_id", "/change/123")
                self.rr._set_output("status", "PENDING")

            with open(output_path, "r") as f:
                contents = f.read()

            self.assertIn("change_id=/change/123\n", contents)
            self.assertIn("status=PENDING\n", contents)
        finally:
            os.unlink(output_path)

    def test_no_op_when_github_output_not_set(self):
        env = os.environ.copy()
        env.pop("GITHUB_OUTPUT", None)
        with patch.dict(os.environ, env, clear=True):
            self.rr._set_output("key", "value")


class TestConnect(unittest.TestCase):

    def setUp(self):
        self.rr = AWSRoute53RecordSet()

    @patch("change.boto3.client")
    def test_passes_credentials_when_inputs_set(self, mock_client):
        mock_r53 = MagicMock()
        mock_client.return_value = mock_r53

        env = {
            "INPUT_AWS_ACCESS_KEY_ID": "AKIATEST",
            "INPUT_AWS_SECRET_ACCESS_KEY": "secret123",
        }
        with patch.dict(os.environ, env):
            self.rr._connect()

        mock_client.assert_called_once_with(
            "route53",
            aws_access_key_id="AKIATEST",
            aws_secret_access_key="secret123",
        )

    @patch("change.boto3.client")
    def test_no_credentials_when_inputs_absent(self, mock_client):
        mock_r53 = MagicMock()
        mock_client.return_value = mock_r53

        env = os.environ.copy()
        env.pop("INPUT_AWS_ACCESS_KEY_ID", None)
        env.pop("INPUT_AWS_SECRET_ACCESS_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            self.rr._connect()

        mock_client.assert_called_once_with("route53")

    @patch("change.boto3.client")
    def test_connect_is_idempotent(self, mock_client):
        mock_r53 = MagicMock()
        mock_client.return_value = mock_r53

        self.rr._connect()
        self.rr._connect()
        mock_client.assert_called_once()


class TestBuildRecordSet(unittest.TestCase):

    def setUp(self):
        self.rr = AWSRoute53RecordSet()

    def _base_env(self, **overrides):
        env = {
            "INPUT_AWS_ROUTE53_RR_ACTION": "CREATE",
            "INPUT_AWS_ROUTE53_RR_NAME": "test.example.com",
            "INPUT_AWS_ROUTE53_RR_TYPE": "A",
            "INPUT_AWS_ROUTE53_RR_TTL": "300",
            "INPUT_AWS_ROUTE53_RR_VALUE": "1.2.3.4",
        }
        env.update(overrides)
        return env

    def test_builds_correct_skeleton(self):
        with patch.dict(os.environ, self._base_env(), clear=True):
            result = self.rr._build_record_set()

        self.assertIn("Changes", result)
        change = result["Changes"][0]
        self.assertEqual(change["Action"], "CREATE")
        rrs = change["ResourceRecordSet"]
        self.assertEqual(rrs["Name"], "test.example.com")
        self.assertEqual(rrs["Type"], "A")
        self.assertEqual(rrs["TTL"], 300)
        self.assertEqual(rrs["ResourceRecords"], [{"Value": "1.2.3.4"}])

    def test_includes_comment_when_set(self):
        env = self._base_env(INPUT_AWS_ROUTE53_RR_COMMENT="test comment")
        with patch.dict(os.environ, env, clear=True):
            result = self.rr._build_record_set()

        self.assertEqual(result["Comment"], "test comment")

    def test_no_comment_key_when_unset(self):
        with patch.dict(os.environ, self._base_env(), clear=True):
            result = self.rr._build_record_set()

        self.assertNotIn("Comment", result)

    def test_default_ttl_when_omitted(self):
        env = self._base_env()
        env.pop("INPUT_AWS_ROUTE53_RR_TTL")
        with patch.dict(os.environ, env, clear=True):
            result = self.rr._build_record_set()

        self.assertEqual(result["Changes"][0]["ResourceRecordSet"]["TTL"], DEFAULT_TTL)


class TestChangeOrchestration(unittest.TestCase):
    """Test the full change() method with mocked AWS calls."""

    def _base_env(self):
        return {
            "INPUT_AWS_ROUTE53_RR_ACTION": "UPSERT",
            "INPUT_AWS_ROUTE53_RR_NAME": "api.example.com",
            "INPUT_AWS_ROUTE53_RR_TYPE": "CNAME",
            "INPUT_AWS_ROUTE53_RR_TTL": "600",
            "INPUT_AWS_ROUTE53_RR_VALUE": "lb.example.com",
            "INPUT_AWS_ROUTE53_HOSTED_ZONE_ID": "Z1234567890",
        }

    @patch("change.boto3.client")
    def test_success_writes_outputs(self, mock_client):
        mock_r53 = MagicMock()
        mock_r53.change_resource_record_sets.return_value = {
            "ChangeInfo": {"Id": "/change/ABC123", "Status": "PENDING"},
            "ResponseMetadata": {"HTTPStatusCode": 200},
        }
        mock_client.return_value = mock_r53

        rr = AWSRoute53RecordSet()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            env = self._base_env()
            env["GITHUB_OUTPUT"] = output_path
            with patch.dict(os.environ, env, clear=True):
                rr.change()

            with open(output_path, "r") as f:
                contents = f.read()

            self.assertIn("change_id=/change/ABC123", contents)
            self.assertIn("status=PENDING", contents)
        finally:
            os.unlink(output_path)

    @patch("change.boto3.client")
    def test_failure_writes_error_output_and_exits(self, mock_client):
        mock_r53 = MagicMock()
        mock_r53.change_resource_record_sets.side_effect = Exception("boom")
        mock_client.return_value = mock_r53

        rr = AWSRoute53RecordSet()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            env = self._base_env()
            env["GITHUB_OUTPUT"] = output_path
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    rr.change()
                self.assertEqual(ctx.exception.code, 1)

            with open(output_path, "r") as f:
                contents = f.read()

            self.assertIn("error=", contents)
            self.assertIn("boom", contents)
        finally:
            os.unlink(output_path)

    @patch("change.boto3.client")
    def test_waiter_called_when_wait_is_true(self, mock_client):
        mock_r53 = MagicMock()
        mock_waiter = MagicMock()
        mock_r53.change_resource_record_sets.return_value = {
            "ChangeInfo": {"Id": "/change/W123", "Status": "PENDING"},
            "ResponseMetadata": {"HTTPStatusCode": 200},
        }
        mock_r53.get_waiter.return_value = mock_waiter
        mock_client.return_value = mock_r53

        rr = AWSRoute53RecordSet()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            env = self._base_env()
            env["INPUT_AWS_ROUTE53_WAIT"] = "true"
            env["GITHUB_OUTPUT"] = output_path
            with patch.dict(os.environ, env, clear=True):
                rr.change()

            mock_waiter.wait.assert_called_once()
            call_kwargs = mock_waiter.wait.call_args
            self.assertEqual(call_kwargs.kwargs["Id"], "/change/W123")
        finally:
            os.unlink(output_path)

    @patch("change.boto3.client")
    def test_waiter_not_called_when_wait_is_false(self, mock_client):
        mock_r53 = MagicMock()
        mock_waiter = MagicMock()
        mock_r53.change_resource_record_sets.return_value = {
            "ChangeInfo": {"Id": "/change/NW1", "Status": "PENDING"},
            "ResponseMetadata": {"HTTPStatusCode": 200},
        }
        mock_r53.get_waiter.return_value = mock_waiter
        mock_client.return_value = mock_r53

        rr = AWSRoute53RecordSet()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            env = self._base_env()
            env["INPUT_AWS_ROUTE53_WAIT"] = "false"
            env["GITHUB_OUTPUT"] = output_path
            with patch.dict(os.environ, env, clear=True):
                rr.change()

            mock_waiter.wait.assert_not_called()
        finally:
            os.unlink(output_path)


if __name__ == "__main__":
    unittest.main()
