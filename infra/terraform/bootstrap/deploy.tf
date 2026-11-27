locals {
  deploy_role_arns = {
    for env, prefix in local.name_prefixes :
    env => "arn:aws:iam::${local.account_id}:role${local.bootstrap_path}${prefix}-deploy"
  }
  state_bucket_arn = "arn:aws:s3:::${var.state_bucket}"
}

resource "aws_iam_role" "deploy" {
  for_each             = local.name_prefixes
  name                 = "${each.value}-deploy"
  path                 = local.bootstrap_path
  assume_role_policy   = data.aws_iam_policy_document.github_trust["${each.key}-deploy"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "deploy" {
  for_each = {
    for pair in setproduct(keys(local.name_prefixes), ["read", "resources", "iam", "state", "guardrails"]) :
    "${pair[0]}-${pair[1]}" => { env = pair[0], policy = pair[1] }
  }
  role = aws_iam_role.deploy[each.value.env].name
  policy_arn = {
    read       = aws_iam_policy.deploy_read[each.value.env].arn
    resources  = aws_iam_policy.deploy_resources[each.value.env].arn
    iam        = aws_iam_policy.deploy_iam[each.value.env].arn
    state      = aws_iam_policy.deploy_state[each.value.env].arn
    guardrails = aws_iam_policy.deploy_guardrails[each.value.env].arn
  }[each.value.policy]
}

resource "aws_iam_policy" "deploy_read" {
  for_each = local.name_prefixes
  name     = "${each.value}-deploy-read"
  path     = local.bootstrap_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "DescribeInfrastructure"
      Effect = "Allow"
      Action = [
        "ec2:Describe*",
        "elasticloadbalancing:Describe*",
        "ecs:Describe*",
        "ecs:List*",
        "ecr:Describe*",
        "ecr:List*",
        "ecr:GetAuthorizationToken",
        "rds:Describe*",
        "rds:ListTagsForResource",
        "logs:Describe*",
        "logs:ListTagsForResource",
        "logs:ListTagsLogGroup",
        "cloudwatch:Describe*",
        "cloudwatch:List*",
        "sns:List*",
        "sqs:ListQueues",
        "lambda:List*",
        "lambda:GetEventSourceMapping",
        "lambda:GetAccountSettings",
        "secretsmanager:ListSecrets",
        "s3:ListAllMyBuckets",
        "s3vectors:List*",
        "ssm:DescribeParameters",
        "iam:Get*",
        "iam:List*",
        "kms:DescribeKey",
        "kms:ListAliases",
        "sts:GetCallerIdentity",
        "tag:GetResources",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_policy" "deploy_resources" {
  for_each = local.name_prefixes
  name     = "${each.value}-deploy-resources"
  path     = local.bootstrap_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnvironmentNamedResources"
        Effect = "Allow"
        Action = [
          "s3:*", "sqs:*", "lambda:*", "ecr:*", "s3vectors:*", "secretsmanager:*", "sns:*",
          "ssm:*", "logs:*", "rds:*", "ecs:*", "elasticloadbalancing:*",
        ]
        Resource = [
          "arn:aws:s3:::${each.value}-*",
          "arn:aws:s3:::${each.value}-*/*",
          "arn:aws:sqs:${local.region}:${local.account_id}:${each.value}-*",
          "arn:aws:lambda:${local.region}:${local.account_id}:function:${each.value}-*",
          "arn:aws:ecr:${local.region}:${local.account_id}:repository/${each.value}*",
          "arn:aws:s3vectors:${local.region}:${local.account_id}:bucket/${each.value}-*",
          "arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:${each.value}-*",
          "arn:aws:sns:${local.region}:${local.account_id}:${each.value}-*",
          "arn:aws:ssm:${local.region}:${local.account_id}:parameter/${each.value}/*",
          "arn:aws:logs:${local.region}:${local.account_id}:log-group:/ecs/${each.value}*",
          "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${each.value}-*",
          "arn:aws:rds:${local.region}:${local.account_id}:db:${each.value}-*",
          "arn:aws:rds:${local.region}:${local.account_id}:snapshot:${each.value}-*",
          "arn:aws:rds:${local.region}:${local.account_id}:subgrp:${each.value}-*",
          "arn:aws:rds:${local.region}:${local.account_id}:pg:default.*",
          "arn:aws:rds:${local.region}:${local.account_id}:og:default:*",
          "arn:aws:ecs:${local.region}:${local.account_id}:cluster/${each.value}*",
          "arn:aws:ecs:${local.region}:${local.account_id}:service/${each.value}*/*",
          "arn:aws:ecs:${local.region}:${local.account_id}:task/${each.value}*/*",
          "arn:aws:ecs:${local.region}:${local.account_id}:task-definition/${each.value}-*:*",
          "arn:aws:elasticloadbalancing:${local.region}:${local.account_id}:loadbalancer/app/${each.value}-*/*",
          "arn:aws:elasticloadbalancing:${local.region}:${local.account_id}:targetgroup/${each.value}-*/*",
          "arn:aws:elasticloadbalancing:${local.region}:${local.account_id}:listener/app/${each.value}-*/*",
          "arn:aws:elasticloadbalancing:${local.region}:${local.account_id}:listener-rule/app/${each.value}-*/*",
        ]
      },
      {
        Sid    = "EnvironmentAlarmsAndDashboard"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:DeleteAlarms",
          "cloudwatch:TagResource",
          "cloudwatch:UntagResource",
          "cloudwatch:PutDashboard",
          "cloudwatch:DeleteDashboards",
          "cloudwatch:GetDashboard",
        ]
        Resource = [
          "arn:aws:cloudwatch:${local.region}:${local.account_id}:alarm:${each.value}-*",
          "arn:aws:cloudwatch::${local.account_id}:dashboard/${each.value}*",
        ]
      },
      {
        Sid    = "TriggersOfEnvironmentFunctions"
        Effect = "Allow"
        Action = [
          "lambda:CreateEventSourceMapping",
          "lambda:UpdateEventSourceMapping",
          "lambda:DeleteEventSourceMapping",
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "lambda:FunctionArn" = "arn:aws:lambda:${local.region}:${local.account_id}:function:${each.value}-*"
          }
        }
      },
      {
        Sid      = "TagTriggers"
        Effect   = "Allow"
        Action   = ["lambda:TagResource", "lambda:UntagResource", "lambda:ListTags"]
        Resource = "arn:aws:lambda:${local.region}:${local.account_id}:event-source-mapping:*"
      },
      {
        Sid    = "TaskDefinitions"
        Effect = "Allow"
        Action = [
          "ecs:RegisterTaskDefinition",
          "ecs:DeregisterTaskDefinition",
          "ecs:TagResource",
        ]
        Resource = "*"
      },
      {
        Sid      = "ServicesAddressedById"
        Effect   = "Allow"
        Action   = ["ec2:*", "cognito-idp:*", "ses:*", "bedrock:*"]
        Resource = "*"
        Condition = {
          StringEquals = { "aws:RequestedRegion" = local.region }
        }
      },
      {
        Sid      = "GlobalEdge"
        Effect   = "Allow"
        Action   = "cloudfront:*"
        Resource = "*"
      },
      {
        Sid      = "EncryptWithAwsManagedKeys"
        Effect   = "Allow"
        Action   = ["kms:CreateGrant", "kms:Decrypt", "kms:GenerateDataKey*", "kms:Encrypt"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = [
              "rds.${local.region}.amazonaws.com",
              "secretsmanager.${local.region}.amazonaws.com",
            ]
          }
        }
      },
    ]
  })
}

resource "aws_iam_policy" "deploy_iam" {
  for_each = local.name_prefixes
  name     = "${each.value}-deploy-iam"
  path     = local.bootstrap_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RolesWithTheBoundary"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:PutRolePermissionsBoundary",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
        ]
        Resource = "arn:aws:iam::${local.account_id}:role/${each.value}/*"
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.boundary[each.key].arn }
        }
      },
      {
        Sid    = "EnvironmentRoles"
        Effect = "Allow"
        Action = [
          "iam:DeleteRole",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:UpdateRole",
          "iam:UpdateRoleDescription",
          "iam:UpdateAssumeRolePolicy",
        ]
        Resource = "arn:aws:iam::${local.account_id}:role/${each.value}/*"
      },
      {
        Sid    = "EnvironmentPolicies"
        Effect = "Allow"
        Action = [
          "iam:CreatePolicy",
          "iam:CreatePolicyVersion",
          "iam:DeletePolicy",
          "iam:DeletePolicyVersion",
          "iam:SetDefaultPolicyVersion",
          "iam:TagPolicy",
          "iam:UntagPolicy",
        ]
        Resource = "arn:aws:iam::${local.account_id}:policy/${each.value}/*"
      },
      {
        Sid      = "PassRolesToTheAppServices"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = "arn:aws:iam::${local.account_id}:role/${each.value}/*"
        Condition = {
          StringEquals = {
            "iam:PassedToService" = [
              "ecs-tasks.amazonaws.com",
              "lambda.amazonaws.com",
              "bedrock.amazonaws.com",
            ]
          }
        }
      },
      {
        Sid      = "ServiceLinkedRoles"
        Effect   = "Allow"
        Action   = "iam:CreateServiceLinkedRole"
        Resource = "*"
        Condition = {
          StringEquals = {
            "iam:AWSServiceName" = [
              "ecs.amazonaws.com",
              "elasticloadbalancing.amazonaws.com",
              "rds.amazonaws.com",
              "vpcorigin.cloudfront.amazonaws.com",
            ]
          }
        }
      },
      {
        Sid    = "DeletePreT14Roles"
        Effect = "Allow"
        Action = [
          "iam:DeleteRole",
          "iam:DeleteRolePolicy",
          "iam:DetachRolePolicy",
          "iam:DeletePolicy",
          "iam:DeletePolicyVersion",
        ]
        Resource = [
          "arn:aws:iam::${local.account_id}:role/${each.value}-*",
          "arn:aws:iam::${local.account_id}:policy/${each.value}-*",
        ]
      },
    ]
  })
}

resource "aws_iam_policy" "deploy_state" {
  for_each = local.name_prefixes
  name     = "${each.value}-deploy-state"
  path     = local.bootstrap_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListState"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = local.state_bucket_arn
      },
      {
        Sid      = "OwnState"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${local.state_bucket_arn}/${each.key}/terraform.tfstate"
      },
      {
        Sid      = "OwnLock"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${local.state_bucket_arn}/${each.key}/terraform.tfstate.tflock"
      },
    ]
  })
}

resource "aws_iam_policy" "deploy_guardrails" {
  for_each = local.name_prefixes
  name     = "${each.value}-deploy-guardrails"
  path     = local.bootstrap_path
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "NoChangesToThePipelineTrust"
        Effect = "Deny"
        Action = "iam:*"
        Resource = [
          "arn:aws:iam::${local.account_id}:role${local.bootstrap_path}*",
          "arn:aws:iam::${local.account_id}:policy${local.bootstrap_path}*",
          aws_iam_openid_connect_provider.github.arn,
        ]
      },
      {
        Sid    = "NoNewCredentials"
        Effect = "Deny"
        Action = [
          "iam:CreateUser",
          "iam:CreateAccessKey",
          "iam:CreateLoginProfile",
          "iam:UpdateLoginProfile",
          "iam:AttachUserPolicy",
          "iam:PutUserPolicy",
          "iam:AddUserToGroup",
          "iam:DeleteRolePermissionsBoundary",
          "iam:CreateOpenIDConnectProvider",
          "iam:CreateSAMLProvider",
        ]
        Resource = "*"
      },
      {
        Sid      = "NoBootstrapState"
        Effect   = "Deny"
        Action   = ["s3:PutObject", "s3:DeleteObject*", "s3:PutBucketPolicy", "s3:DeleteBucketPolicy"]
        Resource = [local.state_bucket_arn, "${local.state_bucket_arn}/bootstrap/*"]
      },
      {
        Sid      = "NoOtherEnvironments"
        Effect   = "Deny"
        Action   = "*"
        Resource = "*"
        Condition = {
          StringNotEquals = { "aws:ResourceTag/Environment" = each.key }
          Null            = { "aws:ResourceTag/Environment" = "false" }
        }
      },
      {
        Sid      = "NoResourcesForOtherEnvironments"
        Effect   = "Deny"
        Action   = "*"
        Resource = "*"
        Condition = {
          StringNotEquals = { "aws:RequestTag/Environment" = each.key }
          Null            = { "aws:RequestTag/Environment" = "false" }
        }
      },
    ]
  })
}
