output "queue_arn" {
  value = aws_sqs_queue.extraction.arn
}

output "queue_url" {
  value = aws_sqs_queue.extraction.url
}

output "worker_policy_arn" {
  value = aws_iam_policy.worker.arn
}
