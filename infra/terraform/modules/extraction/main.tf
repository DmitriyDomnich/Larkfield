data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  inference_profile_arn = "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_inference_profile_id}"
  # the profile id without its geography prefix ("eu.") is the foundation model it routes to
  foundation_model_id = join(".", slice(split(".", var.bedrock_inference_profile_id), 1, length(split(".", var.bedrock_inference_profile_id))))
}

# dead letter queue (DLQ) for failed messages
resource "aws_sqs_queue" "extraction_dlq" {
  name                      = "${var.project_name}-extraction-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "extraction" {
  name = "${var.project_name}-extraction"

  visibility_timeout_seconds = 180
  receive_wait_time_seconds  = 20
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.extraction_dlq.arn
    maxReceiveCount     = var.max_receives
  })
}

# only S3 events from the documents bucket may send to the queue
resource "aws_sqs_queue_policy" "extraction" {
  queue_url = aws_sqs_queue.extraction.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowDocumentsBucketEvents"
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.extraction.arn
      Condition = {
        ArnEquals    = { "aws:SourceArn" = var.documents_bucket_arn }
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

resource "aws_iam_policy" "worker" {
  name = "${var.project_name}-extraction-worker"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReceiveUploadEvents"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility"]
        Resource = aws_sqs_queue.extraction.arn
      },
      {
        Sid      = "ReadClaimFiles"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion", "s3:DeleteObject", "s3:DeleteObjectVersion"]
        Resource = "${var.documents_bucket_arn}/claims/*"
      },
      {
        Sid      = "RequestReviews"
        Effect   = "Allow"
        Action   = "sqs:SendMessage"
        Resource = var.review_queue_arn
      },
      {
        Sid      = "InvokeInferenceProfile"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = local.inference_profile_arn
      },
      {
        Sid      = "InvokeModelThroughProfile"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = "arn:aws:bedrock:*::foundation-model/${local.foundation_model_id}"
        Condition = {
          StringEquals = { "bedrock:InferenceProfileArn" = local.inference_profile_arn }
        }
      },
    ]
  })
}

# every upload under claims/ POST becomes a message
resource "aws_s3_bucket_notification" "uploads" {
  bucket     = var.documents_bucket_name
  depends_on = [aws_sqs_queue_policy.extraction]
  queue {
    queue_arn     = aws_sqs_queue.extraction.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "claims/"
  }
}
