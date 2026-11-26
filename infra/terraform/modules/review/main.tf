# DLQ for review requests that failed every delivery
resource "aws_sqs_queue" "review_dlq" {
  name                      = "${var.project_name}-review-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "review" {
  name = "${var.project_name}-review"

  # one agent run: up to REVIEW_MAX_TURNS model calls
  visibility_timeout_seconds = 300
  receive_wait_time_seconds  = 20
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.review_dlq.arn
    maxReceiveCount     = var.max_receives
  })
}

resource "aws_iam_policy" "worker" {
  name = "${var.project_name}-review-worker"
  path = var.iam_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReceiveReviewRequests"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility"]
        Resource = aws_sqs_queue.review.arn
      },
      {
        # the agent runs on AgentCore; the worker calls only this runtime, through any endpoint
        Sid      = "InvokeReviewAgent"
        Effect   = "Allow"
        Action   = "bedrock-agentcore:InvokeAgentRuntime"
        Resource = [var.agent_runtime_arn, "${var.agent_runtime_arn}/runtime-endpoint/*"]
      },
    ]
  })
}

# the API requests a re-review after a needs_info answer
resource "aws_iam_policy" "api" {
  name = "${var.project_name}-api-review"
  path = var.iam_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "RequestReviews"
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.review.arn
    }]
  })
}
