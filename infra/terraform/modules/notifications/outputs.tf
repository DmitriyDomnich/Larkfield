output "queue_url" {
  value = aws_sqs_queue.notifications.url
}

output "dlq_url" {
  value = aws_sqs_queue.notifications_dlq.url
}

output "sender_policy_arn" {
  value = aws_iam_policy.sender.arn
}
