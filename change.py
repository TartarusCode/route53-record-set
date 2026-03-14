import os
import sys
import json
import logging
from typing import Any, Dict, Optional
import boto3
from botocore.exceptions import ClientError, WaiterError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_TTL = 300
DEFAULT_WAITER_DELAY = 10
DEFAULT_WAITER_MAX_ATTEMPTS = 50
SUPPORTED_RECORD_TYPES = {
    'SOA', 'A', 'TXT', 'NS', 'CNAME', 'MX', 'PTR', 'SRV', 'SPF', 'AAAA'
}
SUPPORTED_ACTIONS = {'CREATE', 'DELETE', 'UPSERT'}


class AWSRoute53RecordSet:
    """
    Primary class for handling AWS Route 53 Record Sets with enhanced error handling and validation.

    This class provides a comprehensive interface for managing Route 53 record sets
    with proper error handling, input validation, and logging.
    """

    def __init__(self) -> None:
        """
        Initialize the Route 53 Record Set manager.

        Sets up the basic structure for managing AWS Route 53 record sets.
        """
        self.client: Optional[Any] = None
        self.waiter: Optional[Any] = None
        self.rr_skeleton: Dict[str, Any] = {}

    def _get_env(self, variable: str, exit_on_missing: bool = True) -> Optional[str]:
        """
        Fetch a variable from the environment with validation.

        Args:
            variable: The environment variable name
            exit_on_missing: Whether to raise if variable is missing

        Returns:
            The environment variable value or None if not found

        Raises:
            NameError: If variable is missing and exit_on_missing is True
        """
        value = os.environ.get(variable)
        if value is None and exit_on_missing:
            error_msg = f"Missing required environment variable: {variable}"
            logger.error(error_msg)
            raise NameError(error_msg)
        return value

    def _set_output(self, name: str, value: str) -> None:
        """Write a key=value pair to $GITHUB_OUTPUT for downstream steps."""
        output_file = os.environ.get("GITHUB_OUTPUT")
        if output_file:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(f"{name}={value}\n")

    def _validate_record_type(self, record_type: str) -> None:
        """
        Validate that the record type is supported.

        Args:
            record_type: The record type to validate

        Raises:
            ValueError: If record type is not supported
        """
        if record_type not in SUPPORTED_RECORD_TYPES:
            error_msg = (
                f"Unsupported record type: {record_type}. "
                f"Supported types: {', '.join(sorted(SUPPORTED_RECORD_TYPES))}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _validate_action(self, action: str) -> None:
        """
        Validate that the action is supported.

        Args:
            action: The action to validate

        Raises:
            ValueError: If action is not supported
        """
        if action not in SUPPORTED_ACTIONS:
            error_msg = (
                f"Unsupported action: {action}. "
                f"Supported actions: {', '.join(sorted(SUPPORTED_ACTIONS))}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _validate_ttl(self, ttl: Optional[str]) -> int:
        """
        Validate and convert TTL value.

        Args:
            ttl: TTL value as string

        Returns:
            TTL as integer

        Raises:
            ValueError: If TTL is invalid
        """
        try:
            ttl_value = int(ttl) if ttl else DEFAULT_TTL
            if ttl_value < 0 or ttl_value > 2147483647:
                raise ValueError("TTL must be between 0 and 2147483647")
            return ttl_value
        except ValueError as e:
            error_msg = f"Invalid TTL value '{ttl}': {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    def _connect(self) -> None:
        """
        Create a new boto3 client for AWS Route 53.

        Bridges INPUT_AWS_ACCESS_KEY_ID / INPUT_AWS_SECRET_ACCESS_KEY
        (set by GitHub Actions for Docker-based actions) into the boto3
        client constructor so that credentials passed via `with:` actually work.
        Falls back to ambient credentials (env vars, instance profile, OIDC) when
        the action inputs are omitted.
        """
        if not self.client:
            logger.info("Initializing AWS Route 53 client")
            try:
                aws_key = self._get_env("INPUT_AWS_ACCESS_KEY_ID", exit_on_missing=False)
                aws_secret = self._get_env("INPUT_AWS_SECRET_ACCESS_KEY", exit_on_missing=False)

                kwargs: Dict[str, str] = {}
                if aws_key and aws_secret:
                    kwargs["aws_access_key_id"] = aws_key
                    kwargs["aws_secret_access_key"] = aws_secret

                self.client = boto3.client("route53", **kwargs)
                self.waiter = self.client.get_waiter("resource_record_sets_changed")
                logger.info("AWS Route 53 client initialized successfully")
            except Exception as e:
                error_msg = f"Failed to initialize AWS Route 53 client: {e}"
                logger.error(error_msg)
                raise

    def _set_comment(self) -> None:
        """Append an additional comment field to the record set if provided."""
        comment = self._get_env("INPUT_AWS_ROUTE53_RR_COMMENT", exit_on_missing=False)
        if comment:
            self.rr_skeleton["Comment"] = comment

    def _set_base_changes(self) -> None:
        """
        Create the base skeleton required for creating a new record set.

        Validates all required inputs and builds the record set structure.
        """
        action = self._get_env("INPUT_AWS_ROUTE53_RR_ACTION")
        self._validate_action(action)

        name = self._get_env("INPUT_AWS_ROUTE53_RR_NAME")
        record_type = self._get_env("INPUT_AWS_ROUTE53_RR_TYPE")
        self._validate_record_type(record_type)

        ttl_str = self._get_env("INPUT_AWS_ROUTE53_RR_TTL", exit_on_missing=False)
        ttl = self._validate_ttl(ttl_str)

        value = self._get_env("INPUT_AWS_ROUTE53_RR_VALUE")

        self.rr_skeleton["Changes"] = [{
            "Action": action,
            "ResourceRecordSet": {
                "Name": name,
                "Type": record_type,
                "TTL": ttl,
                "ResourceRecords": [{"Value": value}]
            }
        }]

        logger.info(
            "Built record set: %s %s record '%s' (TTL: %d)",
            action, record_type, name, ttl
        )

    def _build_record_set(self) -> Dict[str, Any]:
        """
        Build the complete record set structure.

        Returns:
            The complete record set configuration
        """
        self._set_comment()
        self._set_base_changes()
        return self.rr_skeleton

    def _change_record_set(self, record_set: Dict[str, Any]) -> Dict[str, Any]:
        """
        Request the required change at AWS Route 53.

        Args:
            record_set: The record set configuration

        Returns:
            The AWS response

        Raises:
            ClientError: If AWS operation fails
        """
        hosted_zone_id = self._get_env("INPUT_AWS_ROUTE53_HOSTED_ZONE_ID")

        try:
            logger.info("Submitting change to hosted zone: %s", hosted_zone_id)
            result = self.client.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch=record_set
            )
            logger.info("Record set change submitted successfully")
            return result
        except ClientError as e:
            error_msg = f"AWS Route 53 operation failed: {e}"
            logger.error(error_msg)
            raise

    def _wait(self, request_id: str) -> None:
        """
        Wait until the requested operation is finished.

        Args:
            request_id: The AWS request ID

        Raises:
            WaiterError: If waiting fails
        """
        wait_str = self._get_env("INPUT_AWS_ROUTE53_WAIT", exit_on_missing=False)
        if wait_str and wait_str.lower() in ('true', '1', 'yes'):
            try:
                logger.info("Waiting for change to complete: %s", request_id)
                self.waiter.wait(
                    Id=request_id,
                    WaiterConfig={
                        "Delay": DEFAULT_WAITER_DELAY,
                        "MaxAttempts": DEFAULT_WAITER_MAX_ATTEMPTS
                    }
                )
                logger.info("Record set change completed successfully")
            except WaiterError as e:
                error_msg = f"Failed to wait for change completion: {e}"
                logger.error(error_msg)
                raise

    def _obtain_request_id(self, result: Dict[str, Any]) -> str:
        """
        Extract the request ID from the AWS response.

        Args:
            result: The AWS response

        Returns:
            The request ID
        """
        return result["ChangeInfo"]["Id"]

    def _obtain_marshalled_result(self, result: Dict[str, Any]) -> str:
        """
        Extract and format the HTTP response metadata.

        Args:
            result: The AWS response

        Returns:
            Formatted JSON string of response metadata
        """
        return json.dumps(result["ResponseMetadata"], indent=4)

    def change(self) -> None:
        """
        Orchestrates the complete lifecycle: connect, validate, submit, wait,
        and write outputs to $GITHUB_OUTPUT.
        """
        try:
            logger.info("Starting Route 53 record set change")
            self._connect()
            record_set = self._build_record_set()
            result = self._change_record_set(record_set)
            request_id = self._obtain_request_id(result)
            self._wait(request_id)

            self._set_output("change_id", result["ChangeInfo"]["Id"])
            self._set_output("status", result["ChangeInfo"]["Status"])

            output = self._obtain_marshalled_result(result)
            sys.stdout.write(output + "\n")
            logger.info("Route 53 record set change completed successfully")

        except Exception as e:
            error_msg = f"Route 53 record set change failed: {e}"
            logger.error(error_msg)
            self._set_output("error", str(e))
            sys.stderr.write(error_msg + "\n")
            sys.exit(1)


def main() -> None:
    """Main function to handle Route 53 record set changes."""
    try:
        route53_manager = AWSRoute53RecordSet()
        route53_manager.change()
    except Exception as e:
        error_msg = f"Fatal error: {e}"
        logger.error(error_msg)
        sys.stderr.write(error_msg + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
