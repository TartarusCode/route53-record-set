# AWS Route 53 Record Set

This GitHub Action allows you to manage [AWS Route 53](https://aws.amazon.com/route53/) Record Sets with enhanced validation and error handling.

The naming is aligned with the official interface: https://docs.aws.amazon.com/cli/latest/reference/route53/change-resource-record-sets.html. There you can find possible variations for every Input this GitHub Action supports.

Based on [Roosterfish/aws-route53-record-set-action](https://github.com/Roosterfish/aws-route53-record-set-action)

## Features

- **Composite Action**: Runs natively on the runner — no Docker build overhead
- **Enhanced Validation**: Comprehensive input validation for all parameters
- **Error Handling**: Detailed error messages and proper exception handling
- **Logging**: Structured logging for better debugging and monitoring
- **Type Safety**: Full type hints throughout the codebase
- **Security**: Input sanitization and validation
- **Flexibility**: Support for all major DNS record types

## Get Started

### Recommended Usage (OIDC — no long-lived secrets)

Use [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) with OIDC federation to avoid storing static AWS keys:

```yaml
jobs:
  aws_route53:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@8df5847569e6427dd6c4fb1cf565c83acfa8afa7 # v6.0.0
        with:
          role-to-assume: arn:aws:iam::123456789012:role/Route53Role
          aws-region: us-east-1

      - name: "Create an A record set"
        uses: BGarber42/route53-record-set@v1  # pin to a release tag or full SHA
        with:
          aws_route53_hosted_zone_id: ${{ secrets.AWS_ROUTE53_HOSTED_ZONE_ID }}
          aws_route53_rr_action: "CREATE"
          aws_route53_rr_name: "your-fqdn.example.com"
          aws_route53_rr_type: "A"
          aws_route53_rr_ttl: "300"
          aws_route53_rr_value: "1.2.3.4"
```

### Basic Usage (static keys)

> **Note:** Static access keys are supported but discouraged. Prefer OIDC above.

```yaml
jobs:
  aws_route53:
    runs-on: ubuntu-latest
    permissions: {}
    steps:
      - name: "Create an A record set"
        uses: BGarber42/route53-record-set@v1  # pin to a release tag or full SHA
        with:
          aws_access_key_id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws_secret_access_key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws_route53_hosted_zone_id: ${{ secrets.AWS_ROUTE53_HOSTED_ZONE_ID }}
          aws_route53_rr_action: "CREATE"
          aws_route53_rr_name: "your-fqdn.example.com"
          aws_route53_rr_type: "A"
          aws_route53_rr_ttl: "300"
          aws_route53_rr_value: "1.2.3.4"
```

### Advanced Usage

```yaml
jobs:
  aws_route53:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@8df5847569e6427dd6c4fb1cf565c83acfa8afa7 # v6.0.0
        with:
          role-to-assume: arn:aws:iam::123456789012:role/Route53Role
          aws-region: us-east-1

      - name: "Update CNAME record with wait"
        uses: BGarber42/route53-record-set@v1  # pin to a release tag or full SHA
        with:
          aws_route53_hosted_zone_id: ${{ secrets.AWS_ROUTE53_HOSTED_ZONE_ID }}
          aws_route53_rr_action: "UPSERT"
          aws_route53_rr_name: "api.example.com"
          aws_route53_rr_type: "CNAME"
          aws_route53_rr_ttl: "600"
          aws_route53_rr_value: "load-balancer.example.com"
          aws_route53_rr_comment: "Updated via GitHub Actions"
          aws_route53_wait: "true"
        id: route53_update

      - name: "Check result"
        run: |
          echo "Change ID: ${{ steps.route53_update.outputs.change_id }}"
          echo "Status: ${{ steps.route53_update.outputs.status }}"
```

## Security

### Principle of Least Privilege

When consuming this action, lock down your workflow permissions to only what is needed:

```yaml
permissions:
  id-token: write   # only if using OIDC
  contents: read     # only if you need to check out code
```

If your job does not need any GitHub token permissions, set `permissions: {}`.

### Pin Your References

Always reference this action (and any third-party action) by a full SHA or release tag — never by a branch name like `@master`.

## GitHub Action Inputs

The behavior of this Action can be modified with the following Inputs:

| Name | Description | Choices | Required | Default |
|------|-------------|---------|----------|---------|
| `aws_access_key_id` | AWS access key ID (deprecated — prefer OIDC) | | No | |
| `aws_secret_access_key` | AWS secret access key (deprecated — prefer OIDC) | | No | |
| `aws_route53_hosted_zone_id` | The ID of the hosted zone where the record set will be created | | Yes | |
| `aws_route53_rr_action` | The action to perform on the record set | `CREATE`, `DELETE`, `UPSERT` | Yes | |
| `aws_route53_rr_name` | The fully qualified domain name for the record set | | Yes | |
| `aws_route53_rr_type` | The DNS record type | `SOA`, `A`, `TXT`, `NS`, `CNAME`, `MX`, `PTR`, `SRV`, `SPF`, `AAAA` | Yes | |
| `aws_route53_rr_ttl` | The Time To Live value in seconds | 0-2147483647 | No | `300` |
| `aws_route53_rr_value` | The value for the record set | | Yes | |
| `aws_route53_rr_comment` | An optional comment for the record set change | | No | |
| `aws_route53_wait` | Whether to wait for the change to complete | `true`, `false` | No | `false` |

## Outputs

| Name | Description |
|------|-------------|
| `change_id` | The ID of the submitted change |
| `status` | The status of the change operation |
| `error` | Error message if the operation fails |

## Supported Record Types

This GitHub Action supports the following DNS record types:

- **A**: IPv4 address records
- **AAAA**: IPv6 address records
- **CNAME**: Canonical name records
- **MX**: Mail exchange records
- **NS**: Name server records
- **PTR**: Pointer records
- **SOA**: Start of authority records
- **SPF**: Sender Policy Framework records
- **SRV**: Service records
- **TXT**: Text records

## Supported Actions

- **CREATE**: Create a new record set
- **DELETE**: Delete an existing record set
- **UPSERT**: Create or update a record set

## Error Handling

The action includes comprehensive error handling for:

- **Invalid Inputs**: Validation of all input parameters
- **AWS Errors**: Proper handling of AWS API errors
- **Network Issues**: Connection and timeout handling
- **Authentication**: AWS credential validation
- **Record Type Validation**: Ensures only supported record types are used

## Best Practices

1. **Use OIDC**: Prefer OIDC federation over static AWS access keys
2. **Pin References**: Always reference actions by SHA or release tag
3. **Least Privilege**: Set explicit `permissions` on every job
4. **Use Secrets**: Never hardcode credentials — use GitHub encrypted secrets
5. **Use Appropriate TTL**: Set TTL based on your DNS requirements
6. **Wait for Changes**: Use the wait parameter for critical changes
7. **Add Comments**: Include descriptive comments for audit trails
8. **Test in Staging**: Test changes in a staging environment first

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Ensure AWS credentials are properly configured (OIDC role trust policy or static keys)
2. **Invalid Hosted Zone**: Verify the hosted zone ID is correct
3. **Permission Errors**: Ensure IAM permissions include Route 53 access
4. **TTL Validation**: TTL must be between 0 and 2147483647
5. **Record Type Errors**: Only supported record types are allowed

### Debugging

Enable debug logging by setting the `ACTIONS_STEP_DEBUG` secret to `true` in your repository.

## License

The MIT License (MIT)

Copyright (c) 2020 Julian Pelizäus
Copyright (c) 2021 Brent Garber

### Used libraries

https://pypi.org/project/boto3/ licensed under [Apache License 2.0](https://github.com/boto/boto3/blob/develop/LICENSE)
