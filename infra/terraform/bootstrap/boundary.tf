resource "aws_iam_policy" "boundary" {
  for_each = local.name_prefixes
  name     = "${each.value}-boundary"
  path     = local.bootstrap_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EnvironmentObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject*", "s3:PutObject", "s3:DeleteObject*", "s3:ListBucket"]
        Resource = ["arn:aws:s3:::${each.value}-*", "arn:aws:s3:::${each.value}-*/*"]
      },
      {
        Sid    = "EnvironmentQueues"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:SendMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = "arn:aws:sqs:${local.region}:${local.account_id}:${each.value}-*"
      },
      {
        Sid    = "EnvironmentVectors"
        Effect = "Allow"
        Action = [
          "s3vectors:PutVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors",
          "s3vectors:QueryVectors",
          "s3vectors:GetIndex",
        ]
        Resource = "arn:aws:s3vectors:${local.region}:${local.account_id}:bucket/${each.value}-*"
      },
      {
        Sid      = "EnvironmentSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:${each.value}-*"
      },
      {
        Sid    = "AppServices"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Retrieve",
          "cognito-idp:AdminAddUserToGroup",
          "cognito-idp:AdminRemoveUserFromGroup",
          "cognito-idp:AdminListGroupsForUser",
          "cognito-idp:AdminGetUser",
          "cognito-idp:ListUsersInGroup",
          "ses:SendEmail",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
        ]
        Resource = "*"
      },
      {
        Sid      = "NoIam"
        Effect   = "Deny"
        Action   = ["iam:*", "organizations:*", "account:*"]
        Resource = "*"
      },
    ]
  })
}
