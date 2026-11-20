output "deploy_role_arns" {
  value = { for env, role in aws_iam_role.deploy : env => role.arn }
}

output "plan_role_arns" {
  value = { for env, role in aws_iam_role.plan : env => role.arn }
}

output "boundary_arns" {
  value = { for env, policy in aws_iam_policy.boundary : env => policy.arn }
}
