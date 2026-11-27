data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  recipient_emails = setsubtract(toset(var.recipient_emails), [var.sender_email])
  identity_arns = [
    for email in concat([var.sender_email], tolist(local.recipient_emails)) :
    "arn:aws:ses:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:identity/${email}"
  ]
}

# identities belong to the account, not an environment: dev creates them, prod sends from them
resource "aws_sesv2_email_identity" "sender" {
  count          = var.manage_email_identities ? 1 : 0
  email_identity = var.sender_email
}

moved {
  from = aws_sesv2_email_identity.sender
  to   = aws_sesv2_email_identity.sender[0]
}

resource "aws_sesv2_email_identity" "recipient" {
  for_each       = var.manage_email_identities ? local.recipient_emails : toset([])
  email_identity = each.value
}

resource "aws_sqs_queue" "notifications_dlq" {
  name                      = "${var.project_name}-notifications-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "notifications" {
  name = "${var.project_name}-notifications"

  # AWS recommends at least 6 x the function timeout for a Lambda trigger
  visibility_timeout_seconds = 6 * var.lambda_timeout_seconds
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifications_dlq.arn
    maxReceiveCount     = var.max_receives
  })
}

data "archive_file" "send_notification" {
  type        = "zip"
  source_dir  = "${path.module}/../../../../lambdas/send_notification"
  output_path = "${path.root}/build/send_notification.zip"
  # `make test-unit` writes bytecode when the unit tests import the handler;
  # it would change the hash on every run and the lambda resource would always be recreated
  excludes = ["__pycache__", "__pycache__/**"]
}

resource "aws_iam_role" "send_notification" {
  name                 = "${var.project_name}-send-notification"
  path                 = var.iam_path
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "send_notification_logs" {
  role       = aws_iam_role.send_notification.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "send_notification" {
  name = "send-claim-emails"
  role = aws_iam_role.send_notification.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReceiveNotifications"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.notifications.arn
      },
      {
        Sid      = "LookUpEmployeeEmail"
        Effect   = "Allow"
        Action   = "cognito-idp:AdminGetUser"
        Resource = var.user_pool_arn
      },
      {
        Sid      = "SendEmail"
        Effect   = "Allow"
        Action   = "ses:SendEmail"
        Resource = local.identity_arns
      },
    ]
  })
}

resource "aws_lambda_function" "send_notification" {
  function_name    = "${var.project_name}-send-notification"
  role             = aws_iam_role.send_notification.arn
  runtime          = "python3.13"
  handler          = "handler.handler"
  filename         = data.archive_file.send_notification.output_path
  source_code_hash = data.archive_file.send_notification.output_base64sha256
  timeout          = var.lambda_timeout_seconds

  environment {
    variables = {
      USER_POOL_ID = var.user_pool_id
      SENDER_EMAIL = var.sender_email
    }
  }
}

resource "aws_lambda_event_source_mapping" "notifications" {
  event_source_arn = aws_sqs_queue.notifications.arn
  function_name    = aws_lambda_function.send_notification.arn

  batch_size              = 2
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config {
    maximum_concurrency = 2
  }

  depends_on = [aws_iam_role_policy.send_notification]
}

# the API and workers enqueue notifications (NOTIFICATION_QUEUE_URL)
resource "aws_iam_policy" "sender" {
  name = "${var.project_name}-notification-sender"
  path = var.iam_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "QueueNotifications"
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.notifications.arn
    }]
  })
}
