output "queue_arn" {
  value = aws_sqs_queue.review.arn
}

output "queue_url" {
  value = aws_sqs_queue.review.url
}

output "worker_policy_arn" {
  value = aws_iam_policy.worker.arn
}

output "api_policy_arn" {
  value = aws_iam_policy.api.arn
}

output "dlq_name" {
  value = aws_sqs_queue.review_dlq.name
}
