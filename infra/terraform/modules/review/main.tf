data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  inference_profile_arn = "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_inference_profile_id}"
  # the profile id without its geography prefix ("eu.") is the foundation model it routes to
  foundation_model_id = join(".", slice(split(".", var.bedrock_inference_profile_id), 1, length(split(".", var.bedrock_inference_profile_id))))
  knowledge_base_arn  = "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:knowledge-base/${var.policy_knowledge_base_id}"
}

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
        Sid      = "SearchPolicyKnowledgeBase"
        Effect   = "Allow"
        Action   = "bedrock:Retrieve"
        Resource = local.knowledge_base_arn
      },
      {
        Sid      = "InvokeInferenceProfile"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = local.inference_profile_arn
      },
      {
        Sid      = "InvokeModelThroughProfile"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "arn:aws:bedrock:*::foundation-model/${local.foundation_model_id}"
        Condition = {
          StringEquals = { "bedrock:InferenceProfileArn" = local.inference_profile_arn }
        }
      },
    ]
  })
}
