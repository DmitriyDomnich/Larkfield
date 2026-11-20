resource "aws_iam_role" "plan" {
  for_each             = local.name_prefixes
  name                 = "${each.value}-plan"
  path                 = local.bootstrap_path
  assume_role_policy   = data.aws_iam_policy_document.github_trust["${each.key}-plan"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read_only" {
  for_each   = local.name_prefixes
  role       = aws_iam_role.plan[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "plan" {
  for_each   = local.name_prefixes
  role       = aws_iam_role.plan[each.key].name
  policy_arn = aws_iam_policy.plan[each.key].arn
}

resource "aws_iam_policy" "plan" {
  for_each = local.name_prefixes
  name     = "${each.value}-plan"
  path     = local.bootstrap_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadState"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetObject"]
        Resource = [local.state_bucket_arn, "${local.state_bucket_arn}/${each.key}/terraform.tfstate"]
      },
      {
        Sid      = "HoldTheLock"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${local.state_bucket_arn}/${each.key}/terraform.tfstate.tflock"
      },
      {
        Sid      = "ReadNewerServices"
        Effect   = "Allow"
        Action   = ["s3vectors:Get*", "s3vectors:List*", "bedrock:Get*", "bedrock:List*"]
        Resource = "*"
      },
      {
        # refreshing aws_s3_object (the KB files) calls HeadObject
        Sid    = "NoOtherObjects"
        Effect = "Deny"
        Action = ["s3:GetObject", "s3:GetObjectVersion"]
        NotResource = [
          "${local.state_bucket_arn}/${each.key}/*",
          "arn:aws:s3:::${each.value}-policies-*/*",
          "arn:aws:s3:::${each.value}-clauses-*/*",
        ]
      },
      {
        Sid    = "NoSecretsOrUserData"
        Effect = "Deny"
        Action = [
          "secretsmanager:GetSecretValue",
          "kms:Decrypt",
          "sqs:ReceiveMessage",
          "cognito-idp:ListUsers",
          "cognito-idp:ListUsersInGroup",
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:StartQuery",
        ]
        Resource = "*"
      },
      {
        Sid         = "OnlyTheRuntimeFlag"
        Effect      = "Deny"
        Action      = ["ssm:GetParameter*"]
        NotResource = "arn:aws:ssm:${local.region}:${local.account_id}:parameter/${each.value}/*"
      },
    ]
  })
}
