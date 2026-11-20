output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}

output "dashboard" {
  value = aws_cloudwatch_dashboard.main.dashboard_name
}
