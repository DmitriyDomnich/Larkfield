data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  runtime_name          = replace("${var.project_name}_review", "-", "_")
  inference_profile_arn = "arn:aws:bedrock:${local.region}:${local.account_id}:inference-profile/${var.bedrock_inference_profile_id}"
  foundation_model_id = join(".", slice(split(".", var.bedrock_inference_profile_id), 1, length(split(".", var.bedrock_inference_profile_id))))
  knowledge_base_arn  = "arn:aws:bedrock:${local.region}:${local.account_id}:knowledge-base/${var.policy_knowledge_base_id}"
  log_groups_arn      = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes"
}

resource "aws_iam_role" "runtime" {
  name                 = "${var.project_name}-review-agent-runtime"
  path                 = var.iam_path
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/${local.runtime_name}-*" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "runtime" {
  name = "review-agent"
  role = aws_iam_role.runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PullImage"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
        Resource = var.repository_arn
      },
      {
        Sid      = "EcrToken"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid      = "RuntimeLogGroups"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:DescribeLogStreams"]
        Resource = "${local.log_groups_arn}/${local.runtime_name}-*"
      },
      {
        Sid      = "FindLogGroups"
        Effect   = "Allow"
        Action   = "logs:DescribeLogGroups"
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:log-group:*"
      },
      {
        Sid      = "WriteLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${local.log_groups_arn}/${local.runtime_name}-*:log-stream:*"
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

resource "aws_bedrockagentcore_agent_runtime" "review" {
  agent_runtime_name = local.runtime_name
  description        = "Review agent: proposes a decision on one expense claim"
  role_arn           = aws_iam_role.runtime.arn
  platform_version = "V1"

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${var.repository_url}:${var.image_tag}-agent-runtime"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  # one session per claim: memory stops billing a minute after the answer
  lifecycle_configuration = [{
    idle_runtime_session_timeout = 60
    max_lifetime                 = 28800
  }]

  environment_variables = var.environment_variables

  depends_on = [aws_iam_role_policy.runtime]
}

resource "aws_cloudwatch_log_group" "runtime" {
  name              = "/aws/bedrock-agentcore/runtimes/${aws_bedrockagentcore_agent_runtime.review.agent_runtime_id}-DEFAULT"
  retention_in_days = 14
}
