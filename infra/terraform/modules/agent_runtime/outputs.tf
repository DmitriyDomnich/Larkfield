output "runtime_arn" {
  value = aws_bedrockagentcore_agent_runtime.review.agent_runtime_arn
}

output "runtime_id" {
  value = aws_bedrockagentcore_agent_runtime.review.agent_runtime_id
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.runtime.name
}
