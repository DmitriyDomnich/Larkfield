import {
  to = aws_s3_bucket.state
  id = var.state_bucket
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket

  lifecycle {
    prevent_destroy = true
  }
}

locals {
  state_writes = ["s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion"]
  plan_role_arns = {
    for env, prefix in local.name_prefixes :
    env => "arn:aws:iam::${local.account_id}:role${local.bootstrap_path}${prefix}-plan"
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [{
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [local.state_bucket_arn, "${local.state_bucket_arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }],
      flatten([
        for env in var.environments : [
          {
            Sid       = "OnlyDeployWrites${title(env)}State"
            Effect    = "Deny"
            Principal = "*"
            Action    = local.state_writes
            Resource  = "${local.state_bucket_arn}/${env}/terraform.tfstate"
            Condition = { ArnNotEquals = { "aws:PrincipalArn" = local.deploy_role_arns[env] } }
          },
          {
            Sid       = "OnlyDeployAndPlanLock${title(env)}"
            Effect    = "Deny"
            Principal = "*"
            Action    = local.state_writes
            Resource  = "${local.state_bucket_arn}/${env}/terraform.tfstate.tflock"
            Condition = {
              ArnNotEquals = {
                "aws:PrincipalArn" = [local.deploy_role_arns[env], local.plan_role_arns[env]]
              }
            }
          },
        ]
      ]),
      [{
        Sid       = "NoPipelineRoleWritesBootstrapState"
        Effect    = "Deny"
        Principal = "*"
        Action    = local.state_writes
        Resource  = "${local.state_bucket_arn}/bootstrap/*"
        Condition = {
          ArnLike = { "aws:PrincipalArn" = "arn:aws:iam::${local.account_id}:role${local.bootstrap_path}*" }
        }
      }],
    )
  })
}
